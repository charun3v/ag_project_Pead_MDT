from django import forms
from .models import (
    Patient, ClinicalDetails, MDTConsensus,
    BloodInvestigation, ImagingInvestigation, PathologyInvestigation, MolecularInvestigation,
    State, District, PrimarySite, BloodSpecimenType, ImagingType, ImagingSite,
    PathologySpecimenType, MolecularTestType, UserProfile, DiscussionPurpose
)
from django.contrib.auth.models import User


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            'mr_no', 'name', 'sex', 'date_of_birth', 'diagnosis',
            'primary_treatment_site', 'laterality', 'phone', 'phone_alternate',
            'notes', 'address', 'country', 'state', 'district', 'pincode', 'digipin'
        ]
        widgets = {
            'mr_no': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. MR00123'}),
            'name': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Full Patient Name'}),
            'sex': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date', 'id': 'id_dob'}),
            'diagnosis': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. Ewing Sarcoma, Neuroblastoma'}),
            'primary_treatment_site': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'list': 'primary_sites_list', 'placeholder': 'e.g. Abdomen, Femur'}),
            'laterality': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'phone': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Primary Phone'}),
            'phone_alternate': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Alternate Phone'}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'Clinical or demographic notes...'}),
            'address': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Residential Address'}),
            'country': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'id': 'id_country'}),
            'state': forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'id_state'}),
            'district': forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'id_district'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'PIN Code'}),
            'digipin': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Digipin if available'}),
        }


class ClinicalDetailsForm(forms.ModelForm):
    class Meta:
        model = ClinicalDetails
        fields = [
            'height', 'weight', 'stage', 'diagnosis', 'date_mdt_planned',
            'presenting_complaints', 'examination_findings',
            'prev_tx_history', 'discussion_purpose', 'mdt_discussion_for'
        ]
        widgets = {
            'height': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'id': 'id_height', 'placeholder': 'cm'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'id': 'id_weight', 'placeholder': 'kg'}),
            'stage': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. Stage III / High Risk'}),
            'diagnosis': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Episode Diagnosis (cascades to master on save)'}),
            'date_mdt_planned': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'presenting_complaints': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Presenting symptoms, duration, clinical course...'}),
            'examination_findings': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'General vitals, systemic examination and local physical findings...'}),
            'prev_tx_history': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Prior chemotherapy protocols, surgical resections, radiotherapy details, and treatment response...'}),
            'discussion_purpose': forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'id_discussion_purpose'}),
            'mdt_discussion_for': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Specific clinical questions for the multidisciplinary panel to deliberate...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['discussion_purpose'].queryset = DiscussionPurpose.objects.filter(is_active=True).order_by('display_order', 'name')
        self.fields['discussion_purpose'].empty_label = "-- Select MDT Discussion Purpose --"



class MDTConsensusForm(forms.ModelForm):
    class Meta:
        model = MDTConsensus
        fields = [
            'date_mdt_conducted', 'attendees', 'mdt_discussion', 'consensus', 'followup_actions'
        ]
        widgets = {
            'date_mdt_conducted': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'attendees': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. Dr. A (Med Onc), Dr. B (Surg Onc), Dr. C (Rad Onc), Dr. D (Path)'}),
            'mdt_discussion': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 4, 'placeholder': 'Multi-specialty discussion points, opinions and deliberations...'}),
            'consensus': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 4, 'placeholder': 'Agreed multidisciplinary consensus decision...'}),
            'followup_actions': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Next chemo cycle, surgery schedule, radiotherapy, follow-up imaging...'}),
        }


class BloodInvestigationForm(forms.ModelForm):
    class Meta:
        model = BloodInvestigation
        fields = ['test_date', 'specimen_type', 'details', 'impression', 'attachment', 'linked_to_mdt']
        widgets = {
            'test_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'specimen_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'details': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'CBC, LFT, KFT, Tumor markers, Cytology...'}),
            'impression': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Summary / Impression'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
            'linked_to_mdt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ImagingInvestigationForm(forms.ModelForm):
    class Meta:
        model = ImagingInvestigation
        fields = ['imaging_date', 'imaging_type', 'site', 'details', 'impression', 'attachment', 'linked_to_mdt']
        widgets = {
            'imaging_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'imaging_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'site': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'details': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'CT / MRI / PET findings, dimensions, vascular encasement...'}),
            'impression': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Conclusion / RECIST Response'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
            'linked_to_mdt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PathologyInvestigationForm(forms.ModelForm):
    class Meta:
        model = PathologyInvestigation
        fields = ['path_date', 'lab_reference_no', 'specimen_type', 'site_of_biopsy', 'details', 'impression', 'attachment', 'linked_to_mdt']
        widgets = {
            'path_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'lab_reference_no': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Biopsy / Block No'}),
            'specimen_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'site_of_biopsy': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Biopsy Anatomical Site'}),
            'details': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'Morphology, IHC markers (CD99, Synapto, Desmin, Ki67)...'}),
            'impression': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Histopathological Diagnosis'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
            'linked_to_mdt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MolecularInvestigationForm(forms.ModelForm):
    class Meta:
        model = MolecularInvestigation
        fields = ['test_date', 'test_type', 'lab_reference_no', 'details', 'impression', 'attachment', 'linked_to_mdt']
        widgets = {
            'test_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'test_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'lab_reference_no': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Lab / Panel Ref No'}),
            'details': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'Translocations (EWSR1, MYCN, ALK, BRAF), NGS, Cytogenetics...'}),
            'impression': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Genomic Status / Targetable Aberration'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
            'linked_to_mdt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
