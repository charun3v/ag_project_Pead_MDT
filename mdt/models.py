from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import math
from datetime import date, datetime, time


# ==========================================
# 1. Lookup / Reference Models
# ==========================================

class State(models.Model):
    state_id = models.PositiveIntegerField(unique=True)
    state_name = models.CharField(max_length=255)

    class Meta:
        ordering = ['state_name']

    def __str__(self):
        return self.state_name


class District(models.Model):
    district_id = models.PositiveIntegerField(unique=True)
    district_name = models.CharField(max_length=255)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='districts')

    class Meta:
        ordering = ['district_name']

    def __str__(self):
        return f"{self.district_name} ({self.state.state_name})"


class PrimarySite(models.Model):
    site = models.CharField(max_length=255, unique=True, verbose_name="Primary Anatomical Site")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'site']

    def __str__(self):
        return self.site


class BloodSpecimenType(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Specimen / Test Type")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class ImagingType(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Imaging Modality")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class ImagingSite(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Anatomical Site")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class PathologySpecimenType(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Pathology Specimen Type")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class MolecularTestType(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Molecular Test Type")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class DiscussionPurpose(models.Model):
    purpose_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True, verbose_name="MDT Discussion Purpose")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "MDT Discussion Purpose"
        verbose_name_plural = "MDT Discussion Purposes"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('Admin', 'Administrator'),
        ('SubAdmin', 'Sub Administrator'),
        ('Consultant', 'Consultant Oncologist'),
        ('Resident', 'Resident / Fellow'),
        ('Front Desk', 'Front Desk'),
        ('Physics', 'Medical Physics'),
        ('Nursing', 'Nursing Staff'),
        ('User', 'General User'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='Consultant')
    user_level = models.CharField(max_length=50, blank=True, null=True)
    prefix = models.CharField(max_length=20, default='Dr.', blank=True, null=True)
    full_name = models.CharField(max_length=150, blank=True, null=True)

    def get_display_name(self):
        name = (self.full_name or self.user.get_full_name() or self.user.username).strip()
        pfx = (self.prefix or '').strip()
        if pfx:
            pfx_clean = pfx.rstrip('.').lower()
            if name.lower().startswith(pfx_clean):
                return name
            return f"{pfx} {name}"
        return name

    def __str__(self):
        return f"{self.get_display_name()} ({self.role})"



# ==========================================
# 2. Patient Master Entity
# ==========================================

class Patient(models.Model):
    SEX_CHOICES = [
        ('F', 'Female'),
        ('M', 'Male'),
        ('O', 'Others'),
    ]
    LATERALITY_CHOICES = [
        ('Left', 'Left'),
        ('Right', 'Right'),
        ('Central', 'Central / Midline'),
    ]

    mr_no = models.CharField(max_length=100, primary_key=True, verbose_name="Medical Record No (MR No)")
    name = models.CharField(max_length=255, verbose_name="Patient Name")
    sex = models.CharField(max_length=5, choices=SEX_CHOICES, default='M')
    date_of_birth = models.DateField(verbose_name="Date of Birth")
    diagnosis = models.CharField(max_length=255, blank=True, null=True, verbose_name="Registered Diagnosis")
    primary_treatment_site = models.CharField(max_length=255, blank=True, null=True, verbose_name="Primary Site")
    laterality = models.CharField(max_length=50, choices=LATERALITY_CHOICES, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    phone_alternate = models.CharField(max_length=20, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=50, default='India')
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=15, blank=True, null=True)
    digipin = models.CharField(max_length=50, blank=True, null=True)
    
    is_locked = models.BooleanField(default=True, verbose_name="Locked for Editing")
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)
    last_modified_by = models.CharField(max_length=100, blank=True, null=True)
    last_modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-entered_on']

    def __str__(self):
        return f"{self.mr_no} - {self.name}"

    def format_age(self, as_of_date=None):
        """
        Paediatric oncology age calculation conforming to mdlAge rule:
        - < 30 days: 'X days'
        - < 1 year: 'X months'
        - 1 to 4 years: 'X yrs Y mo'
        - 5+ years: 'X years'
        """
        if not self.date_of_birth:
            return ""
        
        ref_date = as_of_date or date.today()
        dob = self.date_of_birth
        
        total_days = (ref_date - dob).days
        if total_days < 0:
            return "(future date)"
        
        if total_days < 30:
            return f"{total_days} day{'s' if total_days != 1 else ''}"
        
        # Calculate full years
        years = ref_date.year - dob.year
        if (ref_date.month, ref_date.day) < (dob.month, dob.day):
            years -= 1
        
        # Calculate remaining months
        if (ref_date.month, ref_date.day) >= (dob.month, dob.day):
            months = ref_date.month - dob.month
        else:
            months = 12 - (dob.month - ref_date.month)
        if ref_date.day < dob.day:
            months -= 1
        months = max(0, months)
        
        if years == 0:
            return f"{months} month{'s' if months != 1 else ''}"
        elif years < 5:
            res = f"{years} yr{'s' if years != 1 else ''}"
            if months > 0:
                res += f" {months} mo"
            return res
        else:
            return f"{years} years"


# ==========================================
# 3. Clinical Presentation / Episode Entity
# ==========================================

class ClinicalDetails(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Scheduled', 'Scheduled'),
        ('Approved', 'Approved'),
    ]
    DISCUSSION_CHOICES = [
        ('Initial Staging', 'Initial Staging & Treatment Planning'),
        ('Response Assessment', 'Response Assessment (Post-Neoadjuvant)'),
        ('Surgical Planning', 'Surgical Planning & Resectability'),
        ('Radiotherapy Planning', 'Radiotherapy Planning'),
        ('Recurrence/Progression', 'Disease Recurrence / Progression'),
        ('Palliative/Supportive', 'Palliative & Supportive Care'),
        ('Other', 'Other Discussion'),
    ]

    clinical_id = models.AutoField(primary_key=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='clinical_episodes')
    mdt_id = models.CharField(max_length=50, blank=True, null=True, unique=True, verbose_name="MDT ID")
    
    height = models.FloatField(null=True, blank=True, verbose_name="Height (cm)")
    weight = models.FloatField(null=True, blank=True, verbose_name="Weight (kg)")
    stage = models.CharField(max_length=100, blank=True, null=True)
    presenting_complaints = models.TextField(blank=True, null=True, verbose_name="Presenting Complaints")
    examination_findings = models.TextField(blank=True, null=True, verbose_name="Examination Findings")
    prev_tx_history = models.TextField(blank=True, null=True, verbose_name="Previous Treatment Details")
    diagnosis = models.CharField(max_length=255, blank=True, null=True, verbose_name="Episode Diagnosis")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    discussion_purpose = models.ForeignKey(DiscussionPurpose, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="MDT Discussion Purpose", related_name='clinical_episodes')
    discussion_category = models.CharField(max_length=100, blank=True, null=True, verbose_name="Legacy Discussion Category")
    mdt_discussion_for = models.TextField(blank=True, null=True, verbose_name="Specific Clinical Questions for MDT Panel")
    date_mdt_planned = models.DateField(null=True, blank=True, verbose_name="Planned MDT Date")
    
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    approved_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-clinical_id']

    def __str__(self):
        return f"Clinical #{self.clinical_id} - {self.patient.name} ({self.status})"

    @property
    def discussion_purpose_display(self):
        if self.discussion_purpose:
            return self.discussion_purpose.name
        return self.discussion_category or "Initial Staging"

    @property
    def bsa(self):
        """Mosteller Formula for BSA (m2): sqrt((height * weight) / 3600)"""
        if self.height and self.weight and self.height > 0 and self.weight > 0:
            return round(math.sqrt((self.height * self.weight) / 3600.0), 2)
        return None

    @property
    def bmi(self):
        """Body Mass Index (kg/m2)"""
        if self.height and self.weight and self.height > 0 and self.weight > 0:
            h_meters = self.height / 100.0
            return round(self.weight / (h_meters ** 2), 1)
        return None

    @property
    def is_approved(self):
        return self.status in ['Approved', 'Scheduled']

    @property
    def is_scheduled(self):
        return (self.status in ['Scheduled', 'Approved']) and bool(self.date_mdt_planned)

    @property
    def is_locked_1700(self):
        """
        True if date_mdt_planned is scheduled and current local time has passed 17:00 on that date.
        """
        if not self.date_mdt_planned or self.status == 'Draft':
            return False
        tz = timezone.get_current_timezone()
        deadline = timezone.make_aware(
            datetime.combine(self.date_mdt_planned, time(17, 0, 0)),
            tz
        )
        return timezone.localtime() > deadline

    def get_lock_status(self, user=None):
        """
        Institutional MDT Lock Status:
        - Once scheduled, clinical details remain editable until 17:00 hrs on the day of date_mdt_planned.
        - After 17:00 on that date, it becomes non-editable for all users except Admin / SubAdmin.
        - The only way to make it editable is to re-schedule MDT to a new date.
        """
        is_admin = False
        if user:
            if getattr(user, 'is_superuser', False):
                is_admin = True
            profile = getattr(user, 'profile', None)
            if profile and profile.role in ['Admin', 'SubAdmin']:
                is_admin = True

        if not self.date_mdt_planned or self.status == 'Draft':
            return {
                'is_scheduled': False,
                'is_locked': False,
                'is_admin': is_admin,
                'can_edit': True,
                'deadline_passed': False,
                'deadline': None,
                'badge_text': 'Draft',
                'badge_class': 'badge-draft',
            }

        tz = timezone.get_current_timezone()
        deadline = timezone.make_aware(
            datetime.combine(self.date_mdt_planned, time(17, 0, 0)),
            tz
        )
        now = timezone.localtime()
        deadline_passed = now > deadline

        if deadline_passed:
            can_edit = is_admin
            is_locked = not is_admin
            badge_text = 'Locked (17:00 passed)'
            badge_class = 'bg-danger text-white'
        else:
            can_edit = True
            is_locked = False
            badge_text = f'Scheduled (Editable till {self.date_mdt_planned.strftime("%d-%b")} 17:00)'
            badge_class = 'bg-primary text-white'

        return {
            'is_scheduled': True,
            'is_locked': is_locked,
            'is_admin': is_admin,
            'can_edit': can_edit,
            'deadline_passed': deadline_passed,
            'deadline': deadline,
            'badge_text': badge_text,
            'badge_class': badge_class,
        }


# ==========================================
# 4. MDT Consensus Entity
# ==========================================

class MDTConsensus(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Scheduled', 'Scheduled'),
        ('Approved', 'Approved'),
    ]

    consensus_id = models.AutoField(primary_key=True)
    clinical_details = models.OneToOneField(ClinicalDetails, on_delete=models.CASCADE, related_name='consensus')
    mdt_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="MDT ID")
    
    date_mdt_conducted = models.DateField(null=True, blank=True, verbose_name="Date MDT Conducted")
    mdt_discussion = models.TextField(blank=True, null=True, verbose_name="MDT Discussion")
    consensus = models.TextField(blank=True, null=True, verbose_name="MDT Consensus")
    followup_actions = models.TextField(blank=True, null=True, verbose_name="Follow-up Actions")
    attendees = models.TextField(blank=True, null=True, verbose_name="Participating Specialists / Attendees",
                                 help_text="Specialists present: Med Onc, Surg Onc, Rad Onc, Path, Rad")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    approved_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-consensus_id']

    def __str__(self):
        return f"Consensus for MDT: {self.mdt_id or self.clinical_details.clinical_id} ({self.status})"

    @property
    def is_approved(self):
        return self.status == 'Approved'


# ==========================================
# 5. Diagnostic Investigation Sub-Entities
# ==========================================

class BloodInvestigation(models.Model):
    clinical_details = models.ForeignKey(ClinicalDetails, on_delete=models.CASCADE, related_name='blood_tests')
    test_date = models.DateField(verbose_name="Test Date")
    specimen_type = models.ForeignKey(BloodSpecimenType, on_delete=models.PROTECT, verbose_name="Specimen / Test Type")
    details = models.TextField(verbose_name="Details / Findings")
    impression = models.TextField(blank=True, null=True, verbose_name="Impression / Summary")
    attachment = models.FileField(upload_to='investigations/blood/', null=True, blank=True, verbose_name="Report PDF/File")
    linked_to_mdt = models.BooleanField(default=True)
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['test_date', 'id']

    def __str__(self):
        return f"Blood: {self.specimen_type} ({self.test_date})"


class ImagingInvestigation(models.Model):
    clinical_details = models.ForeignKey(ClinicalDetails, on_delete=models.CASCADE, related_name='imaging_tests')
    imaging_date = models.DateField(verbose_name="Imaging Date")
    imaging_type = models.ForeignKey(ImagingType, on_delete=models.PROTECT, verbose_name="Modality")
    site = models.ForeignKey(ImagingSite, on_delete=models.PROTECT, verbose_name="Anatomical Site")
    details = models.TextField(verbose_name="Radiology Findings")
    impression = models.TextField(default='', verbose_name="Overall Imaging Impression / Conclusion")
    attachment = models.FileField(upload_to='investigations/imaging/', null=True, blank=True, verbose_name="Imaging / Report File")
    linked_to_mdt = models.BooleanField(default=True)
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['imaging_date', 'id']

    def __str__(self):
        return f"Imaging: {self.imaging_type} - {self.site} ({self.imaging_date})"


class PathologyInvestigation(models.Model):
    clinical_details = models.ForeignKey(ClinicalDetails, on_delete=models.CASCADE, related_name='pathology_tests')
    path_date = models.DateField(verbose_name="Report Date")
    lab_reference_no = models.CharField(max_length=100, blank=True, null=True, verbose_name="Biopsy / Lab Ref No")
    specimen_type = models.ForeignKey(PathologySpecimenType, on_delete=models.PROTECT, verbose_name="Specimen Type")
    site_of_biopsy = models.CharField(max_length=255, blank=True, null=True, verbose_name="Site of Biopsy")
    details = models.TextField(verbose_name="Microscopic & Gross Findings")
    impression = models.TextField(blank=True, null=True, verbose_name="Histopathological Diagnosis / Impression")
    attachment = models.FileField(upload_to='investigations/pathology/', null=True, blank=True, verbose_name="Pathology Report File")
    linked_to_mdt = models.BooleanField(default=True)
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['path_date', 'id']

    def __str__(self):
        return f"Pathology: {self.specimen_type} ({self.path_date})"


class MolecularInvestigation(models.Model):
    clinical_details = models.ForeignKey(ClinicalDetails, on_delete=models.CASCADE, related_name='molecular_tests')
    test_date = models.DateField(verbose_name="Test Date")
    test_type = models.ForeignKey(MolecularTestType, on_delete=models.PROTECT, verbose_name="Molecular Test Type")
    lab_reference_no = models.CharField(max_length=100, blank=True, null=True, verbose_name="Lab Ref No")
    details = models.TextField(verbose_name="Genomic / Molecular Findings")
    impression = models.TextField(blank=True, null=True, verbose_name="Molecular Interpretation / Targetable Alterations")
    attachment = models.FileField(upload_to='investigations/molecular/', null=True, blank=True, verbose_name="Molecular Report File")
    linked_to_mdt = models.BooleanField(default=True)
    entered_by = models.CharField(max_length=100, blank=True, null=True)
    entered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['test_date', 'id']

    def __str__(self):
        return f"Molecular: {self.test_type} ({self.test_date})"


# ==========================================
# 6. Audit Trail & Sequence Generator
# ==========================================

class AuditLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(default=timezone.now)
    username = models.CharField(max_length=50)
    full_name = models.CharField(max_length=100, blank=True, null=True)
    action = models.CharField(max_length=50)
    table_affected = models.CharField(max_length=50)
    record_ref = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.username}: {self.action} on {self.table_affected} ({self.record_ref})"


class MDTYearSequence(models.Model):
    year = models.PositiveIntegerField(unique=True)
    last_seq = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Year {self.year}: Last Seq {self.last_seq}"
