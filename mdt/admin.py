from django.contrib import admin
from .models import (
    State, District, PrimarySite, BloodSpecimenType, ImagingType, ImagingSite,
    PathologySpecimenType, MolecularTestType, UserProfile, Patient,
    ClinicalDetails, MDTConsensus, BloodInvestigation, ImagingInvestigation,
    PathologyInvestigation, MolecularInvestigation, AuditLog, MDTYearSequence
)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('mr_no', 'name', 'sex', 'date_of_birth', 'diagnosis', 'primary_treatment_site', 'is_locked')
    search_fields = ('mr_no', 'name', 'diagnosis', 'phone')
    list_filter = ('sex', 'laterality', 'is_locked', 'primary_treatment_site')


@admin.register(ClinicalDetails)
class ClinicalDetailsAdmin(admin.ModelAdmin):
    list_display = ('clinical_id', 'patient', 'mdt_id', 'stage', 'status', 'discussion_category', 'date_mdt_planned')
    search_fields = ('clinical_id', 'mdt_id', 'patient__mr_no', 'patient__name', 'diagnosis')
    list_filter = ('status', 'discussion_category', 'date_mdt_planned')


@admin.register(MDTConsensus)
class MDTConsensusAdmin(admin.ModelAdmin):
    list_display = ('consensus_id', 'mdt_id', 'date_mdt_conducted', 'status', 'approved_by')
    search_fields = ('consensus_id', 'mdt_id', 'clinical_details__patient__name')
    list_filter = ('status', 'date_mdt_conducted')


@admin.register(BloodInvestigation)
class BloodInvestigationAdmin(admin.ModelAdmin):
    list_display = ('id', 'clinical_details', 'test_date', 'specimen_type', 'impression')
    list_filter = ('specimen_type', 'test_date')


@admin.register(ImagingInvestigation)
class ImagingInvestigationAdmin(admin.ModelAdmin):
    list_display = ('id', 'clinical_details', 'imaging_date', 'imaging_type', 'site', 'impression')
    list_filter = ('imaging_type', 'site', 'imaging_date')


@admin.register(PathologyInvestigation)
class PathologyInvestigationAdmin(admin.ModelAdmin):
    list_display = ('id', 'clinical_details', 'path_date', 'specimen_type', 'lab_reference_no', 'impression')
    list_filter = ('specimen_type', 'path_date')


@admin.register(MolecularInvestigation)
class MolecularInvestigationAdmin(admin.ModelAdmin):
    list_display = ('id', 'clinical_details', 'test_date', 'test_type', 'lab_reference_no', 'impression')
    list_filter = ('test_type', 'test_date')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('log_id', 'timestamp', 'username', 'action', 'table_affected', 'record_ref')
    search_fields = ('username', 'action', 'table_affected', 'record_ref', 'notes')
    list_filter = ('action', 'table_affected', 'timestamp')
    readonly_fields = [f.name for f in AuditLog._meta.fields]


admin.site.register(State)
admin.site.register(District)
admin.site.register(PrimarySite)
admin.site.register(BloodSpecimenType)
admin.site.register(ImagingType)
admin.site.register(ImagingSite)
admin.site.register(PathologySpecimenType)
admin.site.register(MolecularTestType)
admin.site.register(UserProfile)
admin.site.register(MDTYearSequence)
