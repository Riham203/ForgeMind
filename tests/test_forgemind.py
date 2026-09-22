import csv
import io
import json
import os
import tempfile
import unittest
from datetime import datetime

from app import create_app
from extensions import db
from models import AccountStatus, Asset, BreakdownRecord, BreakdownStatus, Role, User
from services.rag import hash_embed, rag_engine


class BaseTestCase(unittest.TestCase):
    """Base test case creating an isolated test environment."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.vec_fd, self.vec_path = tempfile.mkstemp(suffix=".json")

        class TestConfig:
            TESTING = True
            SECRET_KEY = "test-secret-key"
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.db_path}"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False
            VECTOR_STORE_PATH = self.vec_path
            CHROMA_PATH = tempfile.mkdtemp()
            UPLOAD_FOLDER = tempfile.mkdtemp()
            OPENAI_API_KEY = None
            GROQ_API_KEY = None

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self._seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

        try:
            os.close(self.vec_fd)
            if os.path.exists(self.vec_path):
                os.remove(self.vec_path)
        except Exception:
            pass

    def _seed_test_data(self):
        # Users with different roles and statuses
        self.admin_user = User(
            email="admin@test.local",
            name="System Admin",
            role=Role.ADMIN.value,
            status=AccountStatus.APPROVED.value,
        )
        self.admin_user.set_password("AdminPass123!")

        self.engineer_user = User(
            email="engineer@test.local",
            name="Test Engineer",
            role=Role.ENGINEER.value,
            status=AccountStatus.APPROVED.value,
        )
        self.engineer_user.set_password("EngineerPass123!")

        self.artisan_user = User(
            email="safuan@test.local",
            name="Mr. Mohd Safuan",
            role=Role.ARTISAN.value,
            status=AccountStatus.APPROVED.value,
        )
        self.artisan_user.set_password("SafuanPass123!")

        self.viewer_user = User(
            email="viewer@test.local",
            name="Test Viewer",
            role=Role.VIEWER.value,
            status=AccountStatus.APPROVED.value,
        )
        self.viewer_user.set_password("ViewerPass123!")

        self.pending_user = User(
            email="pending@test.local",
            name="Pending Worker",
            role=Role.ARTISAN.value,
            status=AccountStatus.PENDING.value,
        )
        self.pending_user.set_password("PendingPass123!")

        db.session.add_all([
            self.admin_user,
            self.engineer_user,
            self.artisan_user,
            self.viewer_user,
            self.pending_user,
        ])

        # Test Asset
        self.asset_conveyor = Asset(
            asset_code="21-CV-1013",
            asset_name="Sinter Proportioning Incline Conveyor",
            category="Mechanical",
            area="Proportioning Plant B",
        )
        db.session.add(self.asset_conveyor)

        # Target historical breakdown record R00000053897
        self.target_record = BreakdownRecord(
            code="R00000053897",
            asset_code="21-CV-1013",
            asset_description="Sinter Proportioning Incline Conveyor",
            description="Material flow sensor trip halted feed conveyor line B",
            staff_member="Mr. Mohd Safuan",
            status="Approved",
            received_on=datetime(2026, 2, 14, 8, 30),
            completed_on=datetime(2026, 2, 14, 11, 45),
            category="Instrumentation",
            work_performed="Cleaned blinded inductive proximity flow detector, replaced degraded signal cable, and recalibrated amplifier loop gain.",
            notes="Dust accumulation on sensor face triggered false empty-bed alarm; recommended bi-weekly air purge nozzle.",
            root_cause="Heavy iron ore dust cake blinded optical sensor window.",
            corrective_action="Installed compressed air pulse cleaning kit.",
            lesson_learned="Optical flow sensors require active purging in sintering feed zones.",
            downtime_hours=3.25,
            embedding=[0.05] * 1536,
        )

        # Additional record for filtering and sorting tests
        self.second_record = BreakdownRecord(
            code="R00000053898",
            asset_code="31-EX-2001",
            asset_description="Primary Induced Draft Main Fan Exhauster",
            description="High drive-end bearing vibration exceeded 7.1 mm/s RMS alarm threshold",
            staff_member="Dave Vance",
            status="Completed",
            received_on=datetime(2026, 2, 16, 14, 10),
            completed_on=datetime(2026, 2, 16, 19, 30),
            category="Mechanical",
            work_performed="Balanced impeller dynamically and replenished synthetic ISO VG 220 lubricant.",
            notes="Vibration lowered from 8.2 mm/s to 2.1 mm/s RMS.",
            root_cause="Unbalanced dust accumulation on impeller blades.",
            corrective_action="Cleaned rotor blades and performed field dynamic balancing.",
            lesson_learned="Fan blades require high-pressure wash during scheduled weekly shifts.",
            downtime_hours=5.3,
            embedding=[0.02] * 1536,
        )

        db.session.add_all([self.target_record, self.second_record])
        db.session.commit()

        # Pre-index records in RAG store
        rag_engine.index_record(self.target_record)
        rag_engine.index_record(self.second_record)

    def login_as(self, email, password):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )


class TestModelsAndSchema(BaseTestCase):
    """Test BreakdownRecord and User schema conformity."""

    def test_breakdown_records_tablename(self):
        self.assertEqual(BreakdownRecord.__tablename__, "breakdown_records")

    def test_breakdown_record_fields(self):
        rec = BreakdownRecord.query.filter_by(code="R00000053897").first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.asset_code, "21-CV-1013")
        self.assertEqual(rec.asset_description, "Sinter Proportioning Incline Conveyor")
        self.assertEqual(rec.staff_member, "Mr. Mohd Safuan")
        self.assertEqual(rec.status, "Approved")
        self.assertEqual(rec.category, "Instrumentation")
        self.assertIn("Cleaned blinded inductive proximity", rec.work_performed)
        self.assertIn("Dust accumulation on sensor face", rec.notes)
        self.assertIsNotNone(rec.received_on)
        self.assertIsNotNone(rec.completed_on)

    def test_1536_dimensional_embedding_storage(self):
        rec = BreakdownRecord.query.filter_by(code="R00000053897").first()
        self.assertIsNotNone(rec.embedding)
        self.assertEqual(len(rec.embedding), 1536)

        # Test setting a new 1536-dim vector
        new_vec = [float(i) / 1536.0 for i in range(1536)]
        rec.embedding = new_vec
        db.session.commit()

        reloaded = BreakdownRecord.query.filter_by(code="R00000053897").first()
        self.assertEqual(len(reloaded.embedding), 1536)
        self.assertAlmostEqual(reloaded.embedding[0], 0.0, places=4)
        self.assertAlmostEqual(reloaded.embedding[1535], 1535.0 / 1536.0, places=4)

    def test_breakdown_record_to_dict_keys(self):
        rec = BreakdownRecord.query.filter_by(code="R00000053897").first()
        d = rec.to_dict()
        expected_keys = {
            "id", "code", "receivedOn", "completedOn", "assetCode",
            "assetDescription", "description", "staffMember", "status",
            "workPerformed", "notes", "category", "downtimeHours"
        }
        for key in expected_keys:
            self.assertIn(key, d)
        self.assertEqual(d["code"], "R00000053897")
        self.assertEqual(d["assetCode"], "21-CV-1013")
        self.assertEqual(d["staffMember"], "Mr. Mohd Safuan")

    def test_user_roles_and_permissions(self):
        admin = User.query.filter_by(email="admin@test.local").first()
        artisan = User.query.filter_by(email="safuan@test.local").first()
        viewer = User.query.filter_by(email="viewer@test.local").first()

        self.assertTrue(admin.can_admin())
        self.assertTrue(admin.can_write())
        self.assertTrue(artisan.can_write())
        self.assertFalse(artisan.can_admin())
        self.assertFalse(viewer.can_write())
        self.assertFalse(viewer.can_admin())


class TestAuthenticationAndRBAC(BaseTestCase):
    """Test authentication flows, password security, and RBAC enforcement."""

    def test_login_success_and_logout(self):
        res = self.login_as("admin@test.local", "AdminPass123!")
        self.assertEqual(res.status_code, 200)

        # Logout
        res_logout = self.client.get("/auth/logout", follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)

    def test_login_invalid_credentials(self):
        res = self.login_as("admin@test.local", "WrongPassword!")
        self.assertIn(b"Invalid email or password", res.data)

    def test_pending_user_access_blocked(self):
        self.login_as("pending@test.local", "PendingPass123!")
        # Accessing protected page should redirect to pending notice
        res = self.client.get("/knowledge/", follow_redirects=True)
        self.assertIn(b"Account pending review", res.data)

    def test_registration_creates_pending_status(self):
        res = self.client.post(
            "/auth/register",
            data={
                "name": "New Tech",
                "email": "newtech@test.local",
                "password": "Password123!",
                "role": Role.ARTISAN.value,
            },
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)

        new_user = User.query.filter_by(email="newtech@test.local").first()
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.account_status, AccountStatus.PENDING.value)

    def test_viewer_role_write_restrictions(self):
        # Viewer logs in
        self.login_as("viewer@test.local", "ViewerPass123!")

        # 1. Accessing new breakdown page should redirect back
        res = self.client.get("/knowledge/new", follow_redirects=True)
        self.assertIn(b"read-only", res.data)

        # 2. Attempting inline edit returns 403
        res = self.client.post(
            f"/api/records/{self.target_record.id}/inline-edit",
            json={"workPerformed": "Malicious edit"},
        )
        self.assertEqual(res.status_code, 403)

        # 3. Attempting CSV import returns 403
        data = {"file": (io.BytesIO(b"Code,Asset Code\n"), "test.csv")}
        res = self.client.post("/api/records/import", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 403)

    def test_admin_user_status_and_role_management(self):
        self.login_as("admin@test.local", "AdminPass123!")

        # Approve pending user
        res = self.client.post(
            f"/admin/users/{self.pending_user.id}/status",
            data={"status": AccountStatus.APPROVED.value},
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)
        reloaded = User.query.get(self.pending_user.id)
        self.assertEqual(reloaded.account_status, AccountStatus.APPROVED.value)

        # Promote viewer to engineer
        res = self.client.post(
            f"/admin/users/{self.viewer_user.id}/role",
            data={"role": Role.ENGINEER.value},
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)
        reloaded_viewer = User.query.get(self.viewer_user.id)
        self.assertEqual(reloaded_viewer.role, Role.ENGINEER.value)

    def test_demo_login_endpoint(self):
        res = self.client.get("/auth/demo-login/admin", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"System Admin", res.data)


class TestExcelDashboardAPI(BaseTestCase):
    """Test Excel-style tabular dashboard endpoints, filtering, sorting, inline edit, CSV import/export."""

    def setUp(self):
        super().setUp()
        self.login_as("admin@test.local", "AdminPass123!")

    def test_get_records_list(self):
        res = self.client.get("/api/records")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 2)

        record_codes = [r["code"] for r in data]
        self.assertIn("R00000053897", record_codes)
        self.assertIn("R00000053898", record_codes)

    def test_filter_by_status(self):
        res = self.client.get("/api/records?status=Approved")
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["code"], "R00000053897")

        res_completed = self.client.get("/api/records?status=Completed")
        data_completed = res_completed.get_json()
        self.assertEqual(len(data_completed), 1)
        self.assertEqual(data_completed[0]["code"], "R00000053898")

    def test_filter_by_category(self):
        res = self.client.get("/api/records?category=Instrumentation")
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["code"], "R00000053897")

    def test_filter_by_search_query(self):
        res = self.client.get("/api/records?q=21-CV-1013")
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["code"], "R00000053897")

        res_tech = self.client.get("/api/records?q=Safuan")
        data_tech = res_tech.get_json()
        self.assertEqual(len(data_tech), 1)
        self.assertEqual(data_tech[0]["code"], "R00000053897")

    def test_sorting_records(self):
        # Sort by code ascending
        res_asc = self.client.get("/api/records?sort_by=code&sort_dir=asc")
        data_asc = res_asc.get_json()
        self.assertEqual(data_asc[0]["code"], "R00000053897")
        self.assertEqual(data_asc[1]["code"], "R00000053898")

        # Sort by code descending
        res_desc = self.client.get("/api/records?sort_by=code&sort_dir=desc")
        data_desc = res_desc.get_json()
        self.assertEqual(data_desc[0]["code"], "R00000053898")
        self.assertEqual(data_desc[1]["code"], "R00000053897")

    def test_inline_edit_record(self):
        res = self.client.post(
            f"/api/records/{self.target_record.id}/inline-edit",
            json={
                "workPerformed": "Updated test work: replaced proximity switch and re-aligned bracket.",
                "notes": "Calibrated within 1.5mm gap tolerance.",
                "status": "Completed",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["record"]["workPerformed"], "Updated test work: replaced proximity switch and re-aligned bracket.")
        self.assertEqual(data["record"]["notes"], "Calibrated within 1.5mm gap tolerance.")
        self.assertEqual(data["record"]["status"], "Completed")

        # Verify persisted in database
        reloaded = BreakdownRecord.query.get(self.target_record.id)
        self.assertEqual(reloaded.work_performed, "Updated test work: replaced proximity switch and re-aligned bracket.")
        self.assertEqual(reloaded.notes, "Calibrated within 1.5mm gap tolerance.")
        self.assertEqual(reloaded.status, "Completed")
        self.assertIsNotNone(reloaded.completed_on)

    def test_set_status_endpoint(self):
        res = self.client.post(
            f"/api/records/{self.target_record.id}/status",
            json={"status": "Completed"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["record"]["status"], "Completed")

    def test_csv_export(self):
        res = self.client.get("/api/records/export")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/csv")
        content = res.data.decode("utf-8")

        # Verify CSV header columns match specifications
        expected_columns = [
            "Code", "Received On", "Completed On", "Asset Code",
            "Asset Description", "Description", "Staff Member", "Status",
            "Work Performed", "Notes", "Category"
        ]
        first_line = content.splitlines()[0]
        for col in expected_columns:
            self.assertIn(col, first_line)

        # Verify row content
        self.assertIn("R00000053897", content)
        self.assertIn("21-CV-1013", content)
        self.assertIn("Mr. Mohd Safuan", content)

    def test_csv_import(self):
        csv_data = (
            "Code,Received On,Completed On,Asset Code,Asset Description,Description,Staff Member,Status,Work Performed,Notes,Category\n"
            "R00000053991,2026-02-18 09:00,2026-02-18 11:30,12-PU-104,Raw Water Pump,Low suction pressure trip,Sarah Connor,Approved,Cleaned suction strainer basket,Strainer was clogged with debris,Mechanical\n"
        )
        file_obj = (io.BytesIO(csv_data.encode("utf-8")), "import_test.csv")
        res = self.client.post(
            "/api/records/import",
            data={"file": file_obj},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)

        # Verify record in DB
        imported = BreakdownRecord.query.filter_by(code="R00000053991").first()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.asset_code, "12-PU-104")
        self.assertEqual(imported.staff_member, "Sarah Connor")
        self.assertEqual(imported.status, "Approved")


class TestRAGSystem(BaseTestCase):
    """Test 1536-dimensional semantic vector search and RAG responses."""

    def setUp(self):
        super().setUp()
        self.login_as("admin@test.local", "AdminPass123!")

    def test_vector_dimension(self):
        vec = hash_embed("Test material flow sensor on 21-CV-1013", dim=1536)
        self.assertEqual(len(vec), 1536)

    def test_rag_semantic_search(self):
        query = "Who fixed the flow detection issue on 21-CV-1013 and how?"
        hits = rag_engine.search(query, k=3)
        self.assertTrue(len(hits) > 0)
        top_hit = hits[0]
        self.assertEqual(top_hit["metadata"]["code"], "R00000053897")
        self.assertEqual(top_hit["metadata"]["asset_code"], "21-CV-1013")
        self.assertEqual(top_hit["metadata"]["staff"], "Mr. Mohd Safuan")

    def test_rag_answer_for_target_query(self):
        """Verify the exact prompt: 'Who fixed the flow detection issue on 21-CV-1013 and how?'"""
        query = "Who fixed the flow detection issue on 21-CV-1013 and how?"
        result = rag_engine.answer(query, k=3)

        answer = result["answer"]
        citations = result["citations"]

        # 1. Must identify technician Mr. Mohd Safuan
        self.assertIn("Mohd Safuan", answer)

        # 2. Must identify asset 21-CV-1013
        self.assertIn("21-CV-1013", answer)

        # 3. Must reference record R00000053897
        self.assertIn("R00000053897", answer)

        # 4. Must detail work performed
        self.assertTrue("proximity" in answer.lower() or "flow detector" in answer.lower())

        # 5. Must include citations linking to record
        self.assertTrue(len(citations) > 0)
        self.assertEqual(citations[0]["code"], "R00000053897")
        self.assertEqual(citations[0]["staff"], "Mr. Mohd Safuan")
        self.assertEqual(citations[0]["assetCode"], "21-CV-1013")

    def test_chat_api_endpoint(self):
        res = self.client.post(
            "/api/chat",
            json={"query": "Who fixed the flow detection issue on 21-CV-1013 and how?"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("answer", data)
        self.assertIn("citations", data)
        self.assertIn("Mohd Safuan", data["answer"])
        self.assertIn("21-CV-1013", data["answer"])


if __name__ == "__main__":
    unittest.main()
