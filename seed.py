"""Populate ForgeMind with realistic industrial plant sample data and index RAG vectors."""

from datetime import datetime, timedelta

from app import create_app
from extensions import db
from models import (
    AccountStatus,
    Asset,
    BreakdownRecord,
    BreakdownStatus,
    Role,
    User,
)
from services.rag import rag_engine

sample_assets = [
    {"asset_code": "21-CV-1013", "asset_name": "Proportioning Incline Conveyor", "category": "Conveyors", "area": "Sinter Plant"},
    {"asset_code": "42-LH-4003", "asset_name": "Furnace Hydraulics Pump", "category": "Pumps", "area": "Furnace Floor"},
    {"asset_code": "TX2003", "asset_name": "Main Transformer Unit 3", "category": "Electrical", "area": "Substation B"},
    {"asset_code": "11-FN-2104", "asset_name": "Cooling Tower Fan Drive", "category": "Fans", "area": "Utilities"},
    {"asset_code": "33-PP-0901", "asset_name": "Process Water Pump A", "category": "Pumps", "area": "Pump House"},
    {"asset_code": "18-VB-5510", "asset_name": "Vibrating Feeder Screen", "category": "Conveyors", "area": "Sinter Plant"},
]

sample_users = [
    {"name": "Plant Admin", "email": "admin@forgemind.local", "password": "Admin123!", "role": Role.ADMIN, "status": AccountStatus.APPROVED},
    {"name": "Aisha Rahman", "email": "engineer@forgemind.local", "password": "Engineer123!", "role": Role.ENGINEER, "status": AccountStatus.APPROVED},
    {"name": "Mr. Mohd Safuan", "email": "safuan@forgemind.local", "password": "Artisan123!", "role": Role.ARTISAN, "status": AccountStatus.APPROVED},
    {"name": "Alex Tan", "email": "alex@forgemind.local", "password": "Artisan123!", "role": Role.ARTISAN, "status": AccountStatus.APPROVED},
    {"name": "Priya Nair", "email": "viewer@forgemind.local", "password": "Viewer123!", "role": Role.VIEWER, "status": AccountStatus.APPROVED},
    {"name": "Pending Tech", "email": "pending@forgemind.local", "password": "Pending123!", "role": Role.ARTISAN, "status": AccountStatus.PENDING},
]


def seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        rag_engine.init_app(app)

        users = {}
        for row in sample_users:
            user = User(
                name=row["name"],
                email=row["email"],
                role=row["role"].value if hasattr(row["role"], "value") else str(row["role"]),
                status=row["status"].value if hasattr(row["status"], "value") else str(row["status"]),
                auth_provider="manual",
            )
            user.set_password(row["password"])
            db.session.add(user)
            users[row["email"]] = user

        assets_by_code = {}
        for row in sample_assets:
            asset = Asset(**row)
            db.session.add(asset)
            assets_by_code[row["asset_code"]] = asset
        db.session.flush()

        base = datetime(2024, 3, 1, 8, 0, 0)
        sample_records = [
            {
                "code": "R00000053897",
                "asset_code": "21-CV-1013",
                "asset_description": "Proportioning Incline Conveyor",
                "staff_member": "Mr. Mohd Safuan",
                "category": "Electrical",
                "received_on": base + timedelta(days=11),
                "completed_on": base + timedelta(days=11, hours=3),
                "description": "Flow detection trip on thermal sensor circuit TX2003 flow switch.",
                "work_performed": "Replaced corroded flow switch and re-terminated signal cables inside junction box.",
                "root_cause": "Moisture ingress past degraded gland seal.",
                "corrective_action": "Replaced switch assembly and re-sealed with weather-proof silicone.",
                "notes": "High temperature trip on drive shaft bearing sensor circuit shared with TX2003 flow detection.",
                "lesson_learned": "Check gasket seal integrity during routine PM.",
                "downtime_hours": 2.5,
                "status": "Completed",
            },
            {
                "code": "R00000053912",
                "asset_code": "TX2003",
                "asset_description": "Main Transformer Unit 3",
                "staff_member": "Mr. Mohd Safuan",
                "category": "Instrumentation",
                "received_on": base + timedelta(days=13),
                "completed_on": base + timedelta(days=13, hours=2),
                "description": "Spurious trip on cooling water flow switch TX2003.",
                "work_performed": "Resolved issue on TX2003 by replacing corroded flow switch contacts and isolating the sensor circuit.",
                "root_cause": "Terminal corrosion from water ingress.",
                "corrective_action": "New IP67 gasket and silicone seal on housing.",
                "notes": "Same failure mode as 21-CV-1013 thermal flow circuit.",
                "lesson_learned": "Standardize gland kits for outdoor junction boxes.",
                "downtime_hours": 1.5,
                "status": "Completed",
            },
            {
                "code": "R00000054001",
                "asset_code": "42-LH-4003",
                "asset_description": "Furnace Hydraulics Pump",
                "staff_member": "Alex Tan",
                "category": "Mechanical",
                "received_on": base + timedelta(days=17),
                "completed_on": None,
                "description": "High vibration alert on main hydraulic pump coupling.",
                "work_performed": "Re-aligned shaft coupling and replaced worn rubber buffers. Awaiting post-repair vibration survey.",
                "root_cause": "Misalignment after last rebuild.",
                "corrective_action": "Laser alignment and new coupling inserts.",
                "notes": "Pending reliability engineer sign-off.",
                "lesson_learned": "Record alignment readings in CMMS after every coupling job.",
                "downtime_hours": 4.0,
                "status": "Pending",
            },
            {
                "code": "R00000054110",
                "asset_code": "21-CV-1013",
                "asset_description": "Proportioning Incline Conveyor",
                "staff_member": "Alex Tan",
                "category": "Mechanical",
                "received_on": base + timedelta(days=22),
                "completed_on": base + timedelta(days=22, hours=5),
                "description": "Belt tracking drift and repeated emergency stop on tail pulley.",
                "work_performed": "Adjusted take-up, replaced damaged idler, and reset tracking.",
                "root_cause": "Collapsed idler causing belt wander.",
                "corrective_action": "New idler set and weekly tracking check added to PM.",
                "notes": "Belt tension confirmed within specification.",
                "lesson_learned": "Replace idler bearings proactively during planned stops.",
                "downtime_hours": 5.0,
                "status": "Approved",
            },
            {
                "code": "R00000054220",
                "asset_code": "11-FN-2104",
                "asset_description": "Cooling Tower Fan Drive",
                "staff_member": "Mr. Mohd Safuan",
                "category": "Electrical",
                "received_on": base + timedelta(days=28),
                "completed_on": base + timedelta(days=28, hours=2),
                "description": "VFD overcurrent trip during fan start.",
                "work_performed": "Megger tested motor, cleaned VFD heatsink, updated accel ramp.",
                "root_cause": "Blocked cooling fins on VFD causing derate and trip.",
                "corrective_action": "Added filter cleaning to monthly electrical PM.",
                "notes": "Cleaned heat sink channels with compressed dry air.",
                "lesson_learned": "Monitor cabinet air inlet filter delta P.",
                "downtime_hours": 2.0,
                "status": "Completed",
            },
            {
                "code": "R00000054305",
                "asset_code": "33-PP-0901",
                "asset_description": "Process Water Pump A",
                "staff_member": "Aisha Rahman",
                "category": "Lubrication",
                "received_on": base + timedelta(days=34),
                "completed_on": base + timedelta(days=34, hours=3),
                "description": "Hot bearing and oil discoloration on process water pump.",
                "work_performed": "Drained oil, flushed housing, replaced 6309 bearings, refilled ISO VG 68.",
                "root_cause": "Water contamination in bearing housing.",
                "corrective_action": "New lip seal and oil sample schedule.",
                "notes": "Oil sight glass replaced with clear polycarbonate.",
                "lesson_learned": "Inspect labyrinth seals whenever pump is washed down.",
                "downtime_hours": 3.2,
                "status": "Completed",
            },
            {
                "code": "R00000054440",
                "asset_code": "18-VB-5510",
                "asset_description": "Vibrating Feeder Screen",
                "staff_member": "Alex Tan",
                "category": "Mechanical",
                "received_on": base + timedelta(days=40),
                "completed_on": base + timedelta(days=40, hours=6),
                "description": "Broken coil spring and uneven feed rate on vibrating screen.",
                "work_performed": "Replaced springs as a set, checked stroke with paint marks.",
                "root_cause": "Fatigue of unmatched spare spring from mixed batch.",
                "corrective_action": "Only install matched spring kits.",
                "notes": "Static stroke measured 9.2mm across all four corners.",
                "lesson_learned": "Tag batch lot numbers on heavy springs in store room.",
                "downtime_hours": 6.5,
                "status": "Approved",
            },
            {
                "code": "R00000054512",
                "asset_code": "42-LH-4003",
                "asset_description": "Furnace Hydraulics Pump",
                "staff_member": "Mr. Mohd Safuan",
                "category": "Instrumentation",
                "received_on": base + timedelta(days=48),
                "completed_on": None,
                "description": "Unreliable pressure transmitter reading causing furnace hydraulic interlock.",
                "work_performed": "Calibrated transmitter, found impulse line blockage. Blowdown pending isolation window.",
                "root_cause": "Scale in impulse line.",
                "corrective_action": "Impulse line flush still outstanding.",
                "notes": "Temporary pressure gauge installed at local manifold.",
                "lesson_learned": "Add steam tracing blowdown procedure.",
                "downtime_hours": 1.0,
                "status": "Pending",
            },
            {
                "code": "R00000054600",
                "asset_code": "TX2003",
                "asset_description": "Main Transformer Unit 3",
                "staff_member": "Aisha Rahman",
                "category": "Electrical",
                "received_on": base + timedelta(days=55),
                "completed_on": base + timedelta(days=55, hours=4),
                "description": "Buchholz alarm during rain event on transformer TX2003.",
                "work_performed": "Inspected conservator breather, replaced silica gel, checked wiring to trip circuit.",
                "root_cause": "Saturated silica gel and minor wiring moisture.",
                "corrective_action": "Breather PM interval reduced to 30 days in monsoon.",
                "notes": "Dissolved gas analysis oil samples confirmed normal ppm.",
                "lesson_learned": "Keep spare silica gel charges pre-baked in dry store.",
                "downtime_hours": 3.8,
                "status": "Completed",
            },
            {
                "code": "R00000054721",
                "asset_code": "21-CV-1013",
                "asset_description": "Proportioning Incline Conveyor",
                "staff_member": "Mr. Mohd Safuan",
                "category": "Electrical",
                "received_on": datetime.utcnow() - timedelta(days=4),
                "completed_on": datetime.utcnow() - timedelta(days=4, hours=-2),
                "description": "Drive shaft bearing temperature sensor nuisance trip under load.",
                "work_performed": "Isolated power, tested resistance, replaced corroded flow/temp switch assembly.",
                "root_cause": "Water ingress caused terminal corrosion.",
                "corrective_action": "Sealed housing with IP67 gasket silicone.",
                "notes": "Check gasket seal integrity during routine PM. Shared circuit with TX2003 flow sensor.",
                "lesson_learned": "Check gasket seal integrity during routine PM.",
                "downtime_hours": 3.5,
                "status": "Completed",
            },
        ]

        for row in sample_records:
            rec = BreakdownRecord(
                code=row["code"],
                asset_code=row["asset_code"],
                asset_description=row["asset_description"],
                description=row["description"],
                staff_member=row["staff_member"],
                status=row["status"],
                received_on=row["received_on"],
                completed_on=row.get("completed_on"),
                work_performed=row["work_performed"],
                notes=row.get("notes"),
                category=row.get("category", "Mechanical"),
                root_cause=row.get("root_cause"),
                corrective_action=row.get("corrective_action"),
                lesson_learned=row.get("lesson_learned"),
                downtime_hours=row.get("downtime_hours", 0.0),
                photo_urls=[],
            )
            db.session.add(rec)
            db.session.flush()
            rag_engine.index_record(rec)

        db.session.commit()
        print("Seed complete.")
        print("Admin   : admin@forgemind.local / Admin123!")
        print("Engineer: engineer@forgemind.local / Engineer123!")
        print("Artisan : safuan@forgemind.local / Artisan123!")
        print("Pending : pending@forgemind.local / Pending123!")


if __name__ == "__main__":
    seed()

