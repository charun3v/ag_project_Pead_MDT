from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from .models import MDTYearSequence, AuditLog, Patient, ClinicalDetails, MDTConsensus
from datetime import date


def generate_next_mdt_id(year=None):
    """
    Concurrency-safe sequential MDT ID generation using select_for_update().
    Format: PED + YYYY + 00 + 00001 (e.g. PED20260000001)
    Conforms to existing database sequence.
    """
    cur_year = year or date.today().year
    with transaction.atomic():
        seq_obj, _ = MDTYearSequence.objects.select_for_update().get_or_create(
            year=cur_year, defaults={'last_seq': 0}
        )
        seq_obj.last_seq += 1
        seq_obj.save()
        
        mdt_id = f"PED{cur_year}00{seq_obj.last_seq:05d}"
        return mdt_id


def write_audit_log(user, action, table_affected, record_ref, notes=""):
    """
    Writes a record into the AuditLog table.
    Mirrors Access mdlUtils.WriteAuditLog.
    """
    username = "System"
    full_name = "System"
    
    if user:
        if hasattr(user, 'username'):
            username = user.username
            full_name = getattr(user, 'get_full_name', lambda: '')() or username
            if hasattr(user, 'profile') and user.profile.full_name:
                full_name = user.profile.full_name
        elif isinstance(user, str):
            username = user
            full_name = user
            
    AuditLog.objects.create(
        timestamp=timezone.now(),
        username=username,
        full_name=full_name,
        action=action,
        table_affected=table_affected,
        record_ref=str(record_ref),
        notes=notes or ""
    )


def cascade_diagnosis(patient_mr, new_diagnosis, user=None):
    """
    Cascades episode diagnosis to the master patient record if changed.
    """
    if not patient_mr or not new_diagnosis:
        return
        
    try:
        patient = Patient.objects.get(mr_no=patient_mr)
        old_diag = patient.diagnosis or ""
        new_diag = new_diagnosis.strip()
        
        if old_diag != new_diag:
            patient.diagnosis = new_diag
            patient.save(update_fields=['diagnosis', 'last_modified_on'])
            write_audit_log(
                user, "UPDATE_DIAGNOSIS", "tblPtDetails", patient_mr,
                f"From: '{old_diag}' To: '{new_diag}'"
            )
    except Patient.DoesNotExist:
        pass


def get_consolidated_investigations(clinical_details):
    """
    Returns a unified chronological list of all 4 investigation categories
    for a given ClinicalDetails instance.
    """
    inv_list = []
    
    for b in clinical_details.blood_tests.select_related('specimen_type').all():
        inv_list.append({
            'id': b.id,
            'date': b.test_date,
            'category': 'Hematology / Biochemistry',
            'category_short': 'Blood',
            'badge_class': 'bg-danger-subtle text-danger border border-danger-subtle',
            'icon': 'bi-droplet-fill',
            'type': b.specimen_type.name,
            'details': b.details,
            'impression': b.impression or '',
            'attachment': b.attachment,
            'obj': b,
            'kind': 'blood',
            'delete_url': reverse('investigation_delete', args=['blood', b.id]),
        })
        
    for i in clinical_details.imaging_tests.select_related('imaging_type', 'site').all():
        inv_list.append({
            'id': i.id,
            'date': i.imaging_date,
            'category': 'Imaging / Radiology',
            'category_short': 'Imaging',
            'badge_class': 'bg-primary-subtle text-primary border border-primary-subtle',
            'icon': 'bi-camera-fill',
            'type': f"{i.imaging_type.name} • {i.site.name}",
            'details': i.details,
            'impression': i.impression or '',
            'attachment': i.attachment,
            'obj': i,
            'kind': 'imaging',
            'delete_url': reverse('investigation_delete', args=['imaging', i.id]),
        })
        
    for p in clinical_details.pathology_tests.select_related('specimen_type').all():
        site_str = f" • {p.site_of_biopsy}" if p.site_of_biopsy else ""
        lab_str = f" [Ref: {p.lab_reference_no}]" if p.lab_reference_no else ""
        inv_list.append({
            'id': p.id,
            'date': p.path_date,
            'category': 'Histopathology',
            'category_short': 'Pathology',
            'badge_class': 'bg-warning-subtle text-dark border border-warning-subtle',
            'icon': 'bi-virus',
            'type': f"{p.specimen_type.name}{site_str}{lab_str}",
            'details': p.details,
            'impression': p.impression or '',
            'attachment': p.attachment,
            'obj': p,
            'kind': 'pathology',
            'delete_url': reverse('investigation_delete', args=['pathology', p.id]),
        })
        
    for m in clinical_details.molecular_tests.select_related('test_type').all():
        lab_str = f" [Ref: {m.lab_reference_no}]" if m.lab_reference_no else ""
        inv_list.append({
            'id': m.id,
            'date': m.test_date,
            'category': 'Molecular / Genetics',
            'category_short': 'Molecular',
            'badge_class': 'bg-info-subtle text-info-emphasis border border-info-subtle',
            'icon': 'bi-dna',
            'type': f"{m.test_type.name}{lab_str}",
            'details': m.details,
            'impression': m.impression or '',
            'attachment': m.attachment,
            'obj': m,
            'kind': 'molecular',
            'delete_url': reverse('investigation_delete', args=['molecular', m.id]),
        })
        
    # Sort chronologically by date, then id
    inv_list.sort(key=lambda x: (x['date'] or date.min, x.get('id', 0)))
    return inv_list
