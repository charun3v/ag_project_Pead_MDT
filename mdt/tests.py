from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from mdt.models import (
    Patient, ClinicalDetails, MDTConsensus, State, District, PrimarySite,
    BloodSpecimenType, ImagingType, ImagingSite, PathologySpecimenType, MolecularTestType,
    AuditLog, UserProfile, BloodInvestigation
)
from mdt.services import generate_next_mdt_id, cascade_diagnosis


class PeadMDTTests(TestCase):
    def setUp(self):
        # Setup test user
        self.user = User.objects.create_user(username='drtest', password='password123', first_name='Dr. Test')
        UserProfile.objects.create(user=self.user, role='Consultant', full_name='Dr. Test Oncologist')
        
        self.admin = User.objects.create_superuser(username='adminuser', password='password123', email='admin@test.com')
        UserProfile.objects.create(user=self.admin, role='Admin', full_name='System Admin')

        self.client = Client()
        self.client.login(username='drtest', password='password123')

        # Reference data
        self.state = State.objects.create(state_id=1, state_name='Karnataka')
        self.district = District.objects.create(district_id=1, district_name='Bengaluru Urban', state=self.state)
        self.site = PrimarySite.objects.create(site='Abdomen')
        self.blood_specimen = BloodSpecimenType.objects.create(id=1, name='Blood')
        self.imaging_type = ImagingType.objects.create(id=1, name='CT')
        self.imaging_site = ImagingSite.objects.create(id=1, name='Abdomen')
        self.path_specimen = PathologySpecimenType.objects.create(id=1, name='Biopsy')
        self.mol_type = MolecularTestType.objects.create(id=1, name='FISH')

        # Test Patient
        self.patient = Patient.objects.create(
            mr_no='MR_TEST_999',
            name='Baby Jane Doe',
            sex='F',
            date_of_birth=date.today() - timedelta(days=730), # ~2 years old
            diagnosis='Neuroblastoma',
            primary_treatment_site='Abdomen',
            state=self.state,
            district=self.district,
            entered_by='drtest'
        )

    def test_paediatric_age_formatting(self):
        # 10 days old
        p_neonate = Patient(date_of_birth=date.today() - timedelta(days=10))
        self.assertEqual(p_neonate.format_age(), '10 days')

        # 6 months old
        p_infant = Patient(date_of_birth=date.today() - timedelta(days=180))
        self.assertTrue('month' in p_infant.format_age())

        # 2 years old
        self.assertTrue('2 yr' in self.patient.format_age())

        # 8 years old
        p_older = Patient(date_of_birth=date.today() - timedelta(days=365*8 + 10))
        self.assertTrue('8 years' in p_older.format_age())

    def test_bsa_and_bmi_calculations(self):
        # Height 100 cm, Weight 16 kg
        # BSA = sqrt(100 * 16 / 3600) = sqrt(1600/3600) = sqrt(0.4444) = 0.67 m2
        # BMI = 16 / (1.0^2) = 16.0 kg/m2
        clin = ClinicalDetails.objects.create(
            patient=self.patient,
            height=100.0,
            weight=16.0,
            diagnosis='Neuroblastoma',
            status='Draft'
        )
        self.assertEqual(clin.bsa, 0.67)
        self.assertEqual(clin.bmi, 16.0)

    def test_concurrency_safe_mdt_id_generation(self):
        id1 = generate_next_mdt_id(2026)
        id2 = generate_next_mdt_id(2026)
        self.assertTrue(id1.startswith('PED202600'))
        self.assertTrue(id2.startswith('PED202600'))
        seq1 = int(id1[-5:])
        seq2 = int(id2[-5:])
        self.assertEqual(seq2, seq1 + 1)

    def test_diagnosis_cascading(self):
        self.assertEqual(self.patient.diagnosis, 'Neuroblastoma')
        cascade_diagnosis('MR_TEST_999', 'High-Risk Neuroblastoma', 'drtest')
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.diagnosis, 'High-Risk Neuroblastoma')

        # Verify audit log was recorded
        log = AuditLog.objects.filter(action='UPDATE_DIAGNOSIS', record_ref='MR_TEST_999').first()
        self.assertIsNotNone(log)
        self.assertIn('High-Risk Neuroblastoma', log.notes)

    def test_dashboard_and_search_views(self):
        # Dashboard
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Paediatric Oncology MDT Dashboard')

        # Patient Search
        resp = self.client.get(reverse('patient_search') + '?q=Jane')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Baby Jane Doe')
        self.assertContains(resp, 'MR_TEST_999')

    def test_clinical_approval_workflow(self):
        clin = ClinicalDetails.objects.create(
            patient=self.patient,
            height=90.0,
            weight=14.0,
            diagnosis='Neuroblastoma',
            status='Draft',
            entered_by='drtest'
        )
        
        # Approve Clinical presentation
        resp = self.client.post(reverse('clinical_edit', args=[clin.clinical_id]), {
            'action': 'approve',
            'diagnosis': 'Neuroblastoma Stage 4',
            'height': 90.0,
            'weight': 14.0,
            'stage': 'Stage 4',
            'discussion_category': 'Initial Staging',
            'date_mdt_planned': date.today() + timedelta(days=3),
            'mdt_discussion_for': 'Surgical resectability'
        })
        self.assertEqual(resp.status_code, 302)

        clin.refresh_from_db()
        self.assertEqual(clin.status, 'Approved')
        self.assertIsNotNone(clin.mdt_id)
        self.assertTrue(clin.mdt_id.startswith('PED'))
        self.assertEqual(clin.approved_by, 'drtest')

        # Check MDTConsensus stub was automatically created
        consensus = MDTConsensus.objects.filter(clinical_details=clin).first()
        self.assertIsNotNone(consensus)
        self.assertEqual(consensus.status, 'Draft')

    def test_reports_rendering(self):
        clin = ClinicalDetails.objects.create(
            patient=self.patient,
            height=100.0,
            weight=16.0,
            diagnosis='Neuroblastoma',
            status='Approved',
            mdt_id='PED20260000099'
        )
        consensus = MDTConsensus.objects.create(
            clinical_details=clin,
            mdt_id='PED20260000099',
            date_mdt_conducted=date.today(),
            mdt_discussion='Multi-specialty deliberations',
            consensus='Proceed with 3 cycles induction chemo',
            followup_actions='CT scan after cycle 3',
            status='Approved'
        )

        # Clinical Summary report
        resp_clin = self.client.get(reverse('report_clinical_summary', args=[clin.clinical_id]))
        self.assertEqual(resp_clin.status_code, 200)
        self.assertContains(resp_clin, 'KIDWAI MEMORIAL INSTITUTE OF ONCOLOGY')
        self.assertContains(resp_clin, 'Baby Jane Doe')

        # Full MDT report
        resp_mdt = self.client.get(reverse('report_mdt_full', args=[consensus.consensus_id]))
        self.assertEqual(resp_mdt.status_code, 200)
        self.assertContains(resp_mdt, 'PED20260000099')
        self.assertContains(resp_mdt, 'Proceed with 3 cycles induction chemo')
