from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from mdt.models import (
    Patient, ClinicalDetails, MDTConsensus, State, District, PrimarySite,
    BloodSpecimenType, ImagingType, ImagingSite, PathologySpecimenType, MolecularTestType,
    AuditLog, UserProfile, BloodInvestigation, DiscussionPurpose
)
from mdt.services import generate_next_mdt_id, cascade_diagnosis
from mdt.forms import ImagingInvestigationForm, BloodInvestigationForm, PathologyInvestigationForm, MolecularInvestigationForm


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
        self.purpose = DiscussionPurpose.objects.create(name='Initial Staging & Treatment Planning', display_order=1)

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
            'discussion_purpose': self.purpose.purpose_id,
            'prev_tx_history': 'Prior chemo completed cycle 2',
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

    def test_user_management_by_admin(self):
        admin_client = Client()
        admin_client.login(username='adminuser', password='password123')

        # 1. Access user list
        resp = admin_client.get(reverse('user_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'User Account Management')
        self.assertContains(resp, 'adminuser')

        # 2. Non-admin access should be denied / redirected
        non_admin_client = Client()
        non_admin_client.login(username='drtest', password='password123')
        resp_denied = non_admin_client.get(reverse('user_list'))
        self.assertEqual(resp_denied.status_code, 302)

        # 3. Create new user
        resp_create = admin_client.post(reverse('user_create'), {
            'username': 'newfellow',
            'prefix': 'Dr.',
            'first_name': 'Fellow Oncologist',
            'email': 'fellow@hospital.org',
            'password': 'SafePassword123!',
            'role': 'Resident'
        })
        self.assertEqual(resp_create.status_code, 302)

        created_user = User.objects.filter(username='newfellow').first()
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.profile.prefix, 'Dr.')
        self.assertEqual(created_user.profile.role, 'Resident')
        self.assertEqual(created_user.profile.full_name, 'Fellow Oncologist')

        # Check audit log for user creation
        log = AuditLog.objects.filter(action='USER_CREATE', record_ref='newfellow').first()
        self.assertIsNotNone(log)

        # 4. Edit user
        resp_edit = admin_client.post(reverse('user_edit', args=[created_user.id]), {
            'prefix': 'Dr.',
            'first_name': 'Senior Fellow',
            'email': 'fellow@hospital.org',
            'role': 'Consultant',
            'password': '',
            'is_active': 'on'
        })
        self.assertEqual(resp_edit.status_code, 302)
        created_user.refresh_from_db()
        self.assertEqual(created_user.profile.role, 'Consultant')
        self.assertEqual(created_user.profile.full_name, 'Senior Fellow')

        # 5. Toggle active
        resp_toggle = admin_client.get(reverse('user_toggle_active', args=[created_user.id]))
        self.assertEqual(resp_toggle.status_code, 302)
        created_user.refresh_from_db()
        self.assertFalse(created_user.is_active)

        # 6. Delete user
        resp_del = admin_client.post(reverse('user_delete', args=[created_user.id]), {
            'confirm_delete': 'on'
        })
        self.assertEqual(resp_del.status_code, 302)
        self.assertFalse(User.objects.filter(username='newfellow').exists())

    def test_admin_deletion_patient_and_cascades(self):
        admin_client = Client()
        admin_client.login(username='adminuser', password='password123')

        # Create patient with clinical presentation and blood test
        del_patient = Patient.objects.create(
            mr_no='MR_DEL_001',
            name='Temporary Patient For Delete',
            sex='M',
            date_of_birth=date.today() - timedelta(days=365*3),
            diagnosis='Wilms Tumor',
            entered_by='adminuser'
        )
        clin = ClinicalDetails.objects.create(
            patient=del_patient,
            diagnosis='Wilms Tumor Stage 1',
            status='Approved',
            mdt_id='PED20260000055'
        )
        MDTConsensus.objects.create(
            clinical_details=clin,
            mdt_id='PED20260000055',
            status='Approved',
            consensus='Upfront Nephrectomy'
        )
        BloodInvestigation.objects.create(
            clinical_details=clin,
            test_date=date.today(),
            specimen_type=self.blood_specimen,
            details='CBC normal'
        )

        # GET confirm delete page
        resp_confirm = admin_client.get(reverse('patient_delete', args=[del_patient.mr_no]))
        self.assertEqual(resp_confirm.status_code, 200)
        self.assertContains(resp_confirm, 'Temporary Patient For Delete')
        self.assertContains(resp_confirm, 'Wilms Tumor')

        # POST without checkbox should fail
        resp_fail = admin_client.post(reverse('patient_delete', args=[del_patient.mr_no]), {})
        self.assertEqual(resp_fail.status_code, 200)
        self.assertTrue(Patient.objects.filter(mr_no='MR_DEL_001').exists())

        # POST with confirmation checkbox deletes patient and cascades
        resp_success = admin_client.post(reverse('patient_delete', args=[del_patient.mr_no]), {
            'confirm_delete': 'on'
        })
        self.assertEqual(resp_success.status_code, 302)
        self.assertFalse(Patient.objects.filter(mr_no='MR_DEL_001').exists())
        self.assertFalse(ClinicalDetails.objects.filter(patient__mr_no='MR_DEL_001').exists())
        self.assertFalse(MDTConsensus.objects.filter(mdt_id='PED20260000055').exists())

        # Check deletion logged in audit trail
        log = AuditLog.objects.filter(action='DELETE_PATIENT', record_ref='MR_DEL_001').first()
        self.assertIsNotNone(log)

    def test_admin_deletion_clinical_presentation(self):
        admin_client = Client()
        admin_client.login(username='adminuser', password='password123')

        clin = ClinicalDetails.objects.create(
            patient=self.patient,
            diagnosis='Neuroblastoma',
            status='Draft'
        )
        MDTConsensus.objects.create(
            clinical_details=clin,
            consensus='Draft consensus'
        )

        resp_get = admin_client.get(reverse('clinical_delete', args=[clin.clinical_id]))
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'Permanent MDT Episode Deletion')

        resp_del = admin_client.post(reverse('clinical_delete', args=[clin.clinical_id]), {
            'confirm_delete': 'on'
        })
        self.assertEqual(resp_del.status_code, 302)
        self.assertFalse(ClinicalDetails.objects.filter(clinical_id=clin.clinical_id).exists())

        # Check audit log
        log = AuditLog.objects.filter(action='DELETE_MDT').first()
        self.assertIsNotNone(log)

    def test_data_export_endpoints(self):
        admin_client = Client()
        admin_client.login(username='adminuser', password='password123')

        # 1. Export Hub View
        resp_hub = admin_client.get(reverse('export_hub'))
        self.assertEqual(resp_hub.status_code, 200)
        self.assertContains(resp_hub, 'Clinical Data Export Hub')

        # 2. Patients CSV Export (contains UTF-8 BOM)
        resp_pts = admin_client.get(reverse('export_patients_csv'))
        self.assertEqual(resp_pts.status_code, 200)
        self.assertEqual(resp_pts['Content-Type'], 'text/csv; charset=utf-8')
        content_pts = resp_pts.content.decode('utf-8-sig')
        self.assertIn('Baby Jane Doe', content_pts)
        self.assertIn('MR_TEST_999', content_pts)

        # 3. MDT Presentations CSV Export
        resp_mdt = admin_client.get(reverse('export_mdt_csv'))
        self.assertEqual(resp_mdt.status_code, 200)
        content_mdt = resp_mdt.content.decode('utf-8-sig')
        self.assertIn('Clinical ID', content_mdt)

        # 4. Investigations CSV Export
        resp_inv = admin_client.get(reverse('export_investigations_csv'))
        self.assertEqual(resp_inv.status_code, 200)
        content_inv = resp_inv.content.decode('utf-8-sig')
        self.assertIn('Investigation Type', content_inv)

        # 5. Complete ZIP Export
        resp_zip = admin_client.get(reverse('export_all_zip'))
        self.assertEqual(resp_zip.status_code, 200)
        self.assertEqual(resp_zip['Content-Type'], 'application/zip')
        self.assertTrue(len(resp_zip.content) > 100)

    def test_discussion_purpose_lookup_and_api(self):
        admin_client = Client()
        admin_client.login(username='adminuser', password='password123')

        # 1. Access manage purposes page
        resp = admin_client.get(reverse('manage_purposes'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'MDT Discussion Purpose Reference Table')

        # 2. Add new purpose via page POST
        resp_add = admin_client.post(reverse('manage_purposes'), {
            'action': 'add',
            'name': 'Proton Beam Evaluation',
            'display_order': 20
        })
        self.assertEqual(resp_add.status_code, 302)
        p = DiscussionPurpose.objects.filter(name='Proton Beam Evaluation').first()
        self.assertIsNotNone(p)
        self.assertTrue(p.is_active)

        # 3. Toggle purpose
        resp_toggle = admin_client.post(reverse('manage_purposes'), {
            'action': 'toggle',
            'purpose_id': p.purpose_id
        })
        self.assertEqual(resp_toggle.status_code, 302)
        p.refresh_from_db()
        self.assertFalse(p.is_active)

        # 4. Add purpose via JSON API (AJAX inline add on clinical page)
        resp_api = admin_client.post(reverse('api_add_discussion_purpose'), {
            'name': 'Marrow Assessment'
        })
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json()
        self.assertEqual(data['name'], 'Marrow Assessment')
        self.assertTrue(DiscussionPurpose.objects.filter(name='Marrow Assessment').exists())

        # 5. Drag-and-drop Reorder Purposes via JSON API
        p1 = DiscussionPurpose.objects.create(name='Alpha Purpose', display_order=1)
        p2 = DiscussionPurpose.objects.create(name='Beta Purpose', display_order=2)
        p3 = DiscussionPurpose.objects.create(name='Gamma Purpose', display_order=3)

        # Non-admin forbidden
        non_admin_client = Client()
        non_admin_client.login(username='drtest', password='password123')
        resp_reorder_denied = non_admin_client.post(
            reverse('api_reorder_discussion_purposes'),
            data={'order': [p3.purpose_id, p1.purpose_id, p2.purpose_id]},
            content_type='application/json'
        )
        self.assertEqual(resp_reorder_denied.status_code, 403)

        # Admin allowed
        resp_reorder = admin_client.post(
            reverse('api_reorder_discussion_purposes'),
            data={'order': [p3.purpose_id, p1.purpose_id, p2.purpose_id]},
            content_type='application/json'
        )
        self.assertEqual(resp_reorder.status_code, 200)
        self.assertEqual(resp_reorder.json().get('status'), 'ok')

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        self.assertEqual(p3.display_order, 1)
        self.assertEqual(p1.display_order, 2)
        self.assertEqual(p2.display_order, 3)

    def test_lookup_manager_and_investigations_hub(self):
        admin_client = Client()
        admin_client.login(username='adminuser', password='password123')

        # 1. Lookup Manager View
        resp = admin_client.get(reverse('lookup_manager'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'frmLookupManager')
        self.assertContains(resp, 'Reference Categories')

        # Add Option via Lookup Manager
        resp_add = admin_client.post(reverse('lookup_add', kwargs={'category': 'imaging_type'}), {
            'name_value': 'PET-MRI Hybrid',
            'display_order': 15,
            'is_active': '1'
        })
        self.assertEqual(resp_add.status_code, 302)
        self.assertTrue(ImagingType.objects.filter(name='PET-MRI Hybrid').exists())

        # Toggle Option
        opt = ImagingType.objects.get(name='PET-MRI Hybrid')
        resp_toggle = admin_client.post(reverse('lookup_toggle', kwargs={'category': 'imaging_type', 'item_id': opt.id}))
        self.assertEqual(resp_toggle.status_code, 302)
        opt.refresh_from_db()
        self.assertFalse(opt.is_active)

        # 2. Imaging Study Mandatory Impression Validation
        clin = ClinicalDetails.objects.create(patient=self.patient, status='Draft')
        
        # Missing impression fails validation
        form_invalid = ImagingInvestigationForm(data={
            'imaging_date': date.today(),
            'imaging_type': self.imaging_type.id,
            'site': self.imaging_site.id,
            'details': 'Large pelvic mass',
            'impression': '',  # Empty impression
        })
        self.assertFalse(form_invalid.is_valid())
        self.assertIn('impression', form_invalid.errors)

        # Valid with impression
        form_valid = ImagingInvestigationForm(data={
            'imaging_date': date.today(),
            'imaging_type': self.imaging_type.id,
            'site': self.imaging_site.id,
            'details': 'Large retroperitoneal neuroblastoma',
            'impression': 'Primary retroperitoneal neuroblastoma, encasing renal vessels',
        })
        self.assertTrue(form_valid.is_valid())
        img_study = form_valid.save(commit=False)
        img_study.clinical_details = clin
        img_study.save()
        self.assertIsNotNone(img_study.id)

        # 3. Investigations Hub View
        resp_hub = admin_client.get(reverse('investigations_hub', kwargs={'clinical_id': clin.clinical_id}))
        self.assertEqual(resp_hub.status_code, 200)
        self.assertContains(resp_hub, 'frmInvestigations')
        self.assertContains(resp_hub, 'Diagnostic & Staging Workup')

        # Hub Imaging Tab
        resp_img_tab = admin_client.get(f"{reverse('investigations_hub', kwargs={'clinical_id': clin.clinical_id})}?tab=imaging")
        self.assertEqual(resp_img_tab.status_code, 200)
        self.assertContains(resp_img_tab, 'Primary retroperitoneal neuroblastoma')




