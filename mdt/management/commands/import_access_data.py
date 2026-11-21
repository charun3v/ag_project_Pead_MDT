import os
import pyodbc
from datetime import datetime, date
from django.utils import timezone

def make_aware_dt(dt):
    if dt and isinstance(dt, datetime):
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt
    return None
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from mdt.models import (
    State, District, PrimarySite, BloodSpecimenType, ImagingType, ImagingSite,
    PathologySpecimenType, MolecularTestType, UserProfile, Patient,
    ClinicalDetails, MDTConsensus, BloodInvestigation, ImagingInvestigation,
    PathologyInvestigation, MolecularInvestigation, AuditLog, MDTYearSequence
)


class Command(BaseCommand):
    help = "Imports all data from MS Access database PeadMDT_PRE_Split1.accdb into Django"

    def add_arguments(self, parser):
        parser.add_argument(
            '--db_path',
            type=str,
            default=r"D:\n3v\My projects\Databases\Pead MDT\Base files\PeadMDT_PRE_Split1.accdb",
            help="Path to the Access .accdb file"
        )

    def handle(self, *args, **options):
        db_path = options['db_path']
        self.stdout.write(self.style.NOTICE(f"Connecting to Access DB: {db_path}"))

        if not os.path.exists(db_path):
            self.stderr.write(f"File not found: {db_path}")
            return

        conn_str = f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={db_path};"
        try:
            conn = pyodbc.connect(conn_str)
        except Exception as e:
            self.stderr.write(f"Connection failed: {e}")
            return

        cursor = conn.cursor()

        with transaction.atomic():
            self.import_lookups(cursor)
            self.import_users(cursor)
            self.import_patients(cursor)
            self.import_clinical_details(cursor)
            self.import_mdt_consensus(cursor)
            self.import_investigations(cursor)
            self.import_audit_logs(cursor)
            self.sync_sequence()

        conn.close()
        self.stdout.write(self.style.SUCCESS("All Access data imported successfully!"))

    def import_lookups(self, cursor):
        self.stdout.write("Importing States & Districts...")
        # States
        cursor.execute("SELECT StateID, StateName FROM tblStates ORDER BY StateID")
        for row in cursor.fetchall():
            sid = int(float(row[0])) if row[0] is not None else 0
            sname = str(row[1]).strip() if row[1] else ""
            if sid and sname:
                State.objects.update_or_create(state_id=sid, defaults={'state_name': sname})

        # Districts
        cursor.execute("SELECT DistrictID, DistrictName, StateID FROM tblDistricts ORDER BY DistrictID")
        for row in cursor.fetchall():
            did = int(float(row[0])) if row[0] is not None else 0
            dname = str(row[1]).strip() if row[1] else ""
            sid = int(float(row[2])) if row[2] is not None else 0
            try:
                state_obj = State.objects.get(state_id=sid)
                District.objects.update_or_create(district_id=did, defaults={'district_name': dname, 'state': state_obj})
            except State.DoesNotExist:
                pass

        # PrimarySite
        cursor.execute("SELECT DISTINCT Site FROM tblPrimarysite WHERE Site IS NOT NULL")
        for row in cursor.fetchall():
            s = str(row[0]).strip()
            if s:
                PrimarySite.objects.get_or_create(site=s)

        # BloodSpecimenType
        cursor.execute("SELECT ID, Test_Type_Bcm FROM sbtblBCMinv WHERE Test_Type_Bcm IS NOT NULL ORDER BY ID")
        for row in cursor.fetchall():
            BloodSpecimenType.objects.update_or_create(id=int(row[0]), defaults={'name': str(row[1]).strip()})

        # ImagingType
        cursor.execute("SELECT ID, Test_Type_Imaging FROM sbtblImaging WHERE Test_Type_Imaging IS NOT NULL ORDER BY ID")
        for row in cursor.fetchall():
            ImagingType.objects.update_or_create(id=int(row[0]), defaults={'name': str(row[1]).strip()})

        # ImagingSite
        cursor.execute("SELECT ID, Test_Type_Imaging FROM sbtblImagingSite WHERE Test_Type_Imaging IS NOT NULL ORDER BY ID")
        for row in cursor.fetchall():
            ImagingSite.objects.update_or_create(id=int(row[0]), defaults={'name': str(row[1]).strip()})

        # PathologySpecimenType
        cursor.execute("SELECT ID, Test_Type_Path FROM sbtblPath WHERE Test_Type_Path IS NOT NULL ORDER BY ID")
        for row in cursor.fetchall():
            s = str(row[1]).strip()
            if s:
                PathologySpecimenType.objects.update_or_create(id=int(row[0]), defaults={'name': s})

        # MolecularTestType
        cursor.execute("SELECT ID, Test_Type_Mol FROM sbtblMolecular WHERE Test_Type_Mol IS NOT NULL ORDER BY ID")
        for row in cursor.fetchall():
            MolecularTestType.objects.update_or_create(id=int(row[0]), defaults={'name': str(row[1]).strip()})

    def import_users(self, cursor):
        self.stdout.write("Importing Users...")
        cursor.execute("SELECT Users, FullName, UserLevel, isActive FROM tblUsers")
        for row in cursor.fetchall():
            uname = str(row[0]).strip().lower()
            fname = str(row[1]).strip() if row[1] else uname.capitalize()
            ulevel = str(row[2]).strip() if row[2] else 'User'
            is_active = bool(row[3]) if row[3] is not None else True
            
            role = 'Admin' if ulevel == 'Admin' else 'Consultant'
            
            user, created = User.objects.get_or_create(username=uname)
            if created or not user.has_usable_password():
                user.set_password('admin123')
            user.is_active = is_active
            user.is_staff = (role == 'Admin')
            user.is_superuser = (role == 'Admin')
            user.first_name = fname
            user.save()
            
            UserProfile.objects.update_or_create(
                user=user,
                defaults={'role': role, 'full_name': fname}
            )

    def import_patients(self, cursor):
        self.stdout.write("Importing Patients...")
        cursor.execute("SELECT * FROM tblPtDetails")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            mr = str(d.get('MR_No', '')).strip()
            if not mr:
                continue

            # State & District
            state_obj = None
            dist_obj = None
            if d.get('State'):
                state_obj = State.objects.filter(state_name__iexact=str(d['State']).strip()).first()
            if d.get('District') and state_obj:
                dist_obj = District.objects.filter(district_name__iexact=str(d['District']).strip(), state=state_obj).first()

            dob = d.get('Date_Of_birth')
            if isinstance(dob, datetime):
                dob = dob.date()

            Patient.objects.update_or_create(
                mr_no=mr,
                defaults={
                    'name': str(d.get('Pt_name') or 'Unknown').strip(),
                    'sex': str(d.get('Sex') or 'M').strip()[:5],
                    'date_of_birth': dob or date(2000, 1, 1),
                    'diagnosis': str(d.get('Diagnosis') or '').strip() or None,
                    'primary_treatment_site': str(d.get('Primary_treatment_site') or '').strip() or None,
                    'laterality': str(d.get('Laterality') or '').strip() or None,
                    'phone': str(d.get('Phone') or '').strip() or None,
                    'phone_alternate': str(d.get('Phone_Alternate') or '').strip() or None,
                    'notes': str(d.get('Notes') or '').strip() or None,
                    'address': str(d.get('Address') or '').strip() or None,
                    'country': str(d.get('Country') or 'India').strip(),
                    'state': state_obj,
                    'district': dist_obj,
                    'pincode': str(d.get('Pincode') or '').strip() or None,
                    'digipin': str(d.get('Digipin') or '').strip() or None,
                    'is_locked': True,
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip(),
                }
            )

    def import_clinical_details(self, cursor):
        self.stdout.write("Importing Clinical Details...")
        cursor.execute("SELECT * FROM tblClinicalDetails")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            cid = d.get('ClinicalID')
            mr = str(d.get('MR_No') or '').strip()
            patient = Patient.objects.filter(mr_no__iexact=mr).first()
            if not patient:
                self.stderr.write(f"Warning: Patient not found for MR_No '{mr}' (ClinicalID {cid})")
                continue

            dt_planned = d.get('Date_MDT_Planned')
            if isinstance(dt_planned, datetime):
                dt_planned = dt_planned.date()

            app_on = make_aware_dt(d.get('ApprovedOn'))

            ClinicalDetails.objects.update_or_create(
                clinical_id=cid,
                defaults={
                    'patient': patient,
                    'mdt_id': str(d.get('MDTID') or '').strip() or None,
                    'height': float(d['Height']) if d.get('Height') is not None else None,
                    'weight': float(d['Weight']) if d.get('Weight') is not None else None,
                    'stage': str(d.get('Stage') or '').strip() or None,
                    'presenting_complaints': str(d.get('Presenting_Complaints') or '').strip() or None,
                    'examination_findings': str(d.get('Examination_Findings') or '').strip() or None,
                    'prev_tx_history': str(d.get('Prev_Tx_History') or '').strip() or None,
                    'diagnosis': str(d.get('Diagnosis') or '').strip() or None,
                    'status': str(d.get('Status') or 'Draft').strip(),
                    'mdt_discussion_for': str(d.get('MDT_Discussion_For') or '').strip() or None,
                    'date_mdt_planned': dt_planned,
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip() or None,
                    'approved_by': str(d.get('ApprovedBy') or '').strip() or None,
                    'approved_on': app_on,
                }
            )

    def import_mdt_consensus(self, cursor):
        self.stdout.write("Importing MDT Consensus...")
        cursor.execute("SELECT * FROM tblMDTConsensus")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            mid = d.get('MDTConsensusID')
            cid = d.get('ClinicalID')
            clin_obj = ClinicalDetails.objects.filter(clinical_id=cid).first()
            if not clin_obj:
                continue

            dt_conducted = d.get('Date_MDT_conducted')
            if isinstance(dt_conducted, datetime):
                dt_conducted = dt_conducted.date()

            app_on = make_aware_dt(d.get('ApprovedOn'))

            MDTConsensus.objects.update_or_create(
                consensus_id=mid,
                defaults={
                    'clinical_details': clin_obj,
                    'mdt_id': str(d.get('MDTID') or clin_obj.mdt_id or '').strip() or None,
                    'date_mdt_conducted': dt_conducted,
                    'mdt_discussion': str(d.get('MDT_Discussion') or '').strip() or None,
                    'consensus': str(d.get('MDTConsensus') or '').strip() or None,
                    'followup_actions': str(d.get('FollowUp_Actions') or '').strip() or None,
                    'status': str(d.get('Status') or 'Draft').strip(),
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip() or None,
                    'approved_by': str(d.get('ApprovedBy') or '').strip() or None,
                    'approved_on': app_on,
                }
            )

    def import_investigations(self, cursor):
        self.stdout.write("Importing Diagnostic Investigations...")
        
        # Blood
        cursor.execute("SELECT * FROM tblBlood")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            cid = d.get('ClinicalID')
            clin_obj = ClinicalDetails.objects.filter(clinical_id=cid).first()
            if not clin_obj:
                continue
            
            spec_id = int(d['Specimen_Type']) if str(d.get('Specimen_Type') or '').isdigit() else 1
            spec_obj = BloodSpecimenType.objects.filter(id=spec_id).first() or BloodSpecimenType.objects.first()

            tdate = d.get('Test_date')
            if isinstance(tdate, datetime):
                tdate = tdate.date()

            BloodInvestigation.objects.update_or_create(
                id=d.get('BloodID'),
                defaults={
                    'clinical_details': clin_obj,
                    'test_date': tdate or date.today(),
                    'specimen_type': spec_obj,
                    'details': str(d.get('Details') or '').strip(),
                    'impression': str(d.get('Impression') or '').strip() or None,
                    'linked_to_mdt': bool(d.get('LinkedToMDT', True)),
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip(),
                }
            )

        # Imaging
        cursor.execute("SELECT * FROM tblImaging")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            cid = d.get('ClinicalID')
            clin_obj = ClinicalDetails.objects.filter(clinical_id=cid).first()
            if not clin_obj:
                continue

            img_type_id = int(d['Imaging_type']) if str(d.get('Imaging_type') or '').isdigit() else 1
            type_obj = ImagingType.objects.filter(id=img_type_id).first() or ImagingType.objects.first()

            site_id = int(d['Site']) if str(d.get('Site') or '').isdigit() else 1
            site_obj = ImagingSite.objects.filter(id=site_id).first() or ImagingSite.objects.first()

            idate = d.get('Imaging_Date')
            if isinstance(idate, datetime):
                idate = idate.date()

            ImagingInvestigation.objects.update_or_create(
                id=d.get('ImagingID'),
                defaults={
                    'clinical_details': clin_obj,
                    'imaging_date': idate or date.today(),
                    'imaging_type': type_obj,
                    'site': site_obj,
                    'details': str(d.get('Details') or '').strip(),
                    'impression': str(d.get('Impression') or '').strip() or None,
                    'linked_to_mdt': bool(d.get('LinkedToMDT', True)),
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip(),
                }
            )

        # Pathology
        cursor.execute("SELECT * FROM tblPath")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            cid = d.get('ClinicalID')
            clin_obj = ClinicalDetails.objects.filter(clinical_id=cid).first()
            if not clin_obj:
                continue

            ptype_id = int(d['Specimen_type']) if str(d.get('Specimen_type') or '').isdigit() else 1
            ptype_obj = PathologySpecimenType.objects.filter(id=ptype_id).first() or PathologySpecimenType.objects.first()

            pdate = d.get('Path_Date')
            if isinstance(pdate, datetime):
                pdate = pdate.date()

            PathologyInvestigation.objects.update_or_create(
                id=d.get('PathID'),
                defaults={
                    'clinical_details': clin_obj,
                    'path_date': pdate or date.today(),
                    'lab_reference_no': str(d.get('Lab_Reference_No') or '').strip() or None,
                    'specimen_type': ptype_obj,
                    'site_of_biopsy': str(d.get('Site_Of_Biopsy') or '').strip() or None,
                    'details': str(d.get('Details') or '').strip(),
                    'impression': str(d.get('Impression') or '').strip() or None,
                    'linked_to_mdt': bool(d.get('LinkedToMDT', True)),
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip(),
                }
            )

        # Molecular
        cursor.execute("SELECT * FROM tblMolecular")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            cid = d.get('ClinicalID')
            clin_obj = ClinicalDetails.objects.filter(clinical_id=cid).first()
            if not clin_obj:
                continue

            mtype_id = int(d['Test_Type']) if str(d.get('Test_Type') or '').isdigit() else 1
            mtype_obj = MolecularTestType.objects.filter(id=mtype_id).first() or MolecularTestType.objects.first()

            mdate = d.get('Test_Date')
            if isinstance(mdate, datetime):
                mdate = mdate.date()

            MolecularInvestigation.objects.update_or_create(
                id=d.get('MolecularID'),
                defaults={
                    'clinical_details': clin_obj,
                    'test_date': mdate or date.today(),
                    'test_type': mtype_obj,
                    'lab_reference_no': str(d.get('Lab_Reference_No') or '').strip() or None,
                    'details': str(d.get('Details') or '').strip(),
                    'impression': str(d.get('Impression') or '').strip() or None,
                    'linked_to_mdt': bool(d.get('LinkedToMDT', True)),
                    'entered_by': str(d.get('EnteredBy') or 'admin').strip(),
                }
            )

    def import_audit_logs(self, cursor):
        self.stdout.write("Importing Audit Logs...")
        cursor.execute("SELECT * FROM tblAuditLog ORDER BY LogID")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            lid = d.get('LogID')
            ldt = make_aware_dt(d.get('LogDateTime')) or timezone.now()
            AuditLog.objects.update_or_create(
                log_id=lid,
                defaults={
                    'timestamp': ldt,
                    'username': str(d.get('Username') or 'System').strip(),
                    'full_name': str(d.get('FullName') or '').strip() or None,
                    'action': str(d.get('Action') or '').strip(),
                    'table_affected': str(d.get('TableAffected') or '').strip(),
                    'record_ref': str(d.get('RecordRef') or '').strip(),
                    'notes': str(d.get('Notes') or '').strip() or None,
                }
            )

    def sync_sequence(self):
        # Scan existing MDTIDs to set MDTYearSequence correctly
        import re
        max_seq = 0
        year = date.today().year
        for cd in ClinicalDetails.objects.filter(mdt_id__isnull=False):
            # Format PED20260000007 or PED260000007
            m = re.search(r'PED(\d{4}|\d{2})00(\d+)', cd.mdt_id)
            if m:
                s_val = int(m.group(2))
                if s_val > max_seq:
                    max_seq = s_val
        MDTYearSequence.objects.update_or_create(year=year, defaults={'last_seq': max_seq})
        self.stdout.write(f"Synced MDT Sequence for {year}: Last Seq = {max_seq}")
