import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import db
from signal_flow import (
    add_receiver,
    move_receiver,
    parse_signal_metadata,
    reactivate_receiver,
    remove_receiver,
    sync_signal_endpoints,
)


class SignalFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.TemporaryDirectory()
        cls.test_engine = create_engine(f"sqlite:///{Path(cls.test_dir.name) / 'signal_flow.db'}")

        @event.listens_for(cls.test_engine, "connect")
        def _enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        cls.Session = sessionmaker(bind=cls.test_engine)
        db.Base.metadata.create_all(cls.test_engine)

    @classmethod
    def tearDownClass(cls):
        cls.test_engine.dispose()
        cls.test_dir.cleanup()

    def setUp(self):
        self.session = self.Session()
        self.project = db.Project(name=f"Flow-{id(self)}")
        self.other_project = db.Project(name=f"Other-{id(self)}")
        self.session.add_all([self.project, self.other_project])
        self.session.flush()
        self.signal = db.Signal(
            project_id=self.project.id,
            signal_id="SIG-001",
            name="VehicleSpeed",
            message_name="VCU_Status",
            module="VCU",
            description=(
                "原始DBC接口数据\n总线: PTCAN\n发送节点: VCU\n"
                "接收节点: ICM, GW，ADAS\n来源: PTCAN.dbc"
            ),
        )
        self.session.add(self.signal)
        self.session.commit()

    def tearDown(self):
        self.session.rollback()
        self.session.query(db.ArtifactChangeRecord).filter_by(project_id=self.project.id).delete()
        self.session.query(db.SignalEndpoint).filter_by(project_id=self.project.id).delete()
        self.session.query(db.Signal).filter_by(project_id=self.project.id).delete()
        self.session.query(db.Project).filter(db.Project.id.in_([self.project.id, self.other_project.id])).delete(
            synchronize_session=False
        )
        self.session.commit()
        self.session.close()

    def test_parser_extracts_bus_and_multiple_receivers(self):
        meta = parse_signal_metadata(self.signal)
        self.assertEqual(meta.bus, "PTCAN")
        self.assertEqual(meta.tx, "VCU")
        self.assertEqual(meta.receivers, ("ICM", "GW", "ADAS"))
        self.assertEqual(meta.source, "PTCAN.dbc")

    def test_endpoint_sync_is_idempotent(self):
        first = sync_signal_endpoints(self.session, self.project.id)
        second = sync_signal_endpoints(self.session, self.project.id)
        self.assertEqual(first["tx_added"], 1)
        self.assertEqual(first["rx_added"], 3)
        self.assertEqual(second["tx_added"], 0)
        self.assertEqual(second["rx_added"], 0)
        self.assertEqual(
            self.session.query(db.SignalEndpoint).filter_by(project_id=self.project.id).count(),
            4,
        )

    def test_move_preserves_dbc_endpoint_and_writes_audit(self):
        sync_signal_endpoints(self.session, self.project.id)
        endpoint = self.session.query(db.SignalEndpoint).filter_by(
            project_id=self.project.id,
            signal_id=self.signal.id,
            endpoint_role="Rx",
            ecu_name="ICM",
        ).one()
        move_receiver(
            self.session,
            project_id=self.project.id,
            endpoint_id=endpoint.id,
            new_ecu="CDC",
            reason="网络架构评审调整",
            changed_by="Tester",
        )
        self.session.refresh(endpoint)
        self.assertEqual(endpoint.dbc_ecu_name, "ICM")
        self.assertEqual(endpoint.ecu_name, "CDC")
        self.assertEqual(endpoint.source_kind, "Manual")
        change = self.session.query(db.ArtifactChangeRecord).filter_by(
            project_id=self.project.id,
            artifact_id=endpoint.id,
        ).one()
        self.assertEqual((change.old_value, change.new_value), ("ICM", "CDC"))
        self.assertEqual(change.reason, "网络架构评审调整")

    def test_one_signal_can_have_multiple_receivers(self):
        sync_signal_endpoints(self.session, self.project.id)
        endpoint = add_receiver(
            self.session,
            project_id=self.project.id,
            signal_id=self.signal.id,
            new_ecu="CDC",
            reason="新增并行接收节点",
            changed_by="Tester",
        )
        receivers = self.session.query(db.SignalEndpoint).filter_by(
            project_id=self.project.id,
            signal_id=self.signal.id,
            endpoint_role="Rx",
            is_active=True,
        ).all()
        self.assertEqual({row.ecu_name for row in receivers}, {"ICM", "GW", "ADAS", "CDC"})
        self.assertIsNone(endpoint.dbc_ecu_name)
        self.assertEqual(endpoint.source_kind, "Manual")
        with self.assertRaisesRegex(ValueError, "已经连接"):
            add_receiver(
                self.session,
                project_id=self.project.id,
                signal_id=self.signal.id,
                new_ecu="CDC",
                reason="重复连接",
            )

    def test_remove_and_reactivate_receiver_preserve_provenance(self):
        sync_signal_endpoints(self.session, self.project.id)
        endpoint = self.session.query(db.SignalEndpoint).filter_by(
            project_id=self.project.id,
            signal_id=self.signal.id,
            endpoint_role="Rx",
            ecu_name="ICM",
        ).one()
        remove_receiver(
            self.session,
            project_id=self.project.id,
            endpoint_id=endpoint.id,
            reason="当前项目停用",
        )
        self.session.refresh(endpoint)
        self.assertFalse(endpoint.is_active)
        self.assertEqual(endpoint.dbc_ecu_name, "ICM")
        reactivate_receiver(
            self.session,
            project_id=self.project.id,
            endpoint_id=endpoint.id,
            reason="评审后恢复",
        )
        self.session.refresh(endpoint)
        self.assertTrue(endpoint.is_active)
        changes = self.session.query(db.ArtifactChangeRecord).filter_by(
            project_id=self.project.id,
            artifact_id=endpoint.id,
        ).order_by(db.ArtifactChangeRecord.id).all()
        self.assertEqual([change.change_type for change in changes], ["Remove", "Reactivate"])

    def test_move_is_scoped_to_current_project(self):
        sync_signal_endpoints(self.session, self.project.id)
        endpoint = self.session.query(db.SignalEndpoint).filter_by(
            project_id=self.project.id,
            endpoint_role="Rx",
        ).first()
        with self.assertRaisesRegex(ValueError, "不属于当前车型"):
            move_receiver(
                self.session,
                project_id=self.other_project.id,
                endpoint_id=endpoint.id,
                new_ecu="CDC",
                reason="invalid cross project move",
            )

    def test_move_requires_reason(self):
        sync_signal_endpoints(self.session, self.project.id)
        endpoint = self.session.query(db.SignalEndpoint).filter_by(
            project_id=self.project.id,
            endpoint_role="Rx",
        ).first()
        with self.assertRaisesRegex(ValueError, "变更原因"):
            move_receiver(
                self.session,
                project_id=self.project.id,
                endpoint_id=endpoint.id,
                new_ecu="CDC",
                reason="",
            )


if __name__ == "__main__":
    unittest.main()
