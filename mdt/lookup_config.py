from .models import (
    DiscussionPurpose, PrimarySite, BloodSpecimenType,
    ImagingType, ImagingSite, PathologySpecimenType, MolecularTestType
)

LOOKUP_CONFIG = {
    'purpose': {
        'title': 'MDT Discussion Purposes',
        'icon': '🏷️',
        'table_name': 'tblDiscussionPurpose',
        'model': DiscussionPurpose,
        'pk': 'purpose_id',
        'name_field': 'name',
        'name_label': 'Discussion Purpose Name (e.g. Proton Therapy Review, Marrow Assessment)',
        'description': 'Clinical focus areas, indications, and consensus intents available in case presentations.',
    },
    'primary_site': {
        'title': 'Primary Anatomical Sites',
        'icon': '🏥',
        'table_name': 'tblPrimarySite',
        'model': PrimarySite,
        'pk': 'id',
        'name_field': 'site',
        'name_label': 'Primary Anatomical Site (e.g. Abdomen, Brain, Pelvis, Femur, Thorax, Retroperitoneum)',
        'description': 'Master primary tumor anatomical origins used for patient registration and filtering.',
    },
    'imaging_type': {
        'title': 'Diagnostic Imaging Modalities',
        'icon': '🩻',
        'table_name': 'tblImagingType',
        'model': ImagingType,
        'pk': 'id',
        'name_field': 'name',
        'name_label': 'Modality Name (e.g. CT, MRI, PET-CT, USG, X-Ray, MIBG, Bone Scan)',
        'description': 'Radiological imaging modalities available in diagnostic investigation workups.',
    },
    'imaging_site': {
        'title': 'Imaging Anatomical Sites',
        'icon': '🎯',
        'table_name': 'tblImagingSite',
        'model': ImagingSite,
        'pk': 'id',
        'name_field': 'name',
        'name_label': 'Imaging Anatomical Site (e.g. Brain, Head & Neck, Thorax, Abdomen, Pelvis, Spine, Extremities, Whole Body)',
        'description': 'Target anatomical regions examined during radiological scans.',
    },
    'blood_specimen': {
        'title': 'Blood Specimen & Test Panels',
        'icon': '🩸',
        'table_name': 'tblBloodSpecimenType',
        'model': BloodSpecimenType,
        'pk': 'id',
        'name_field': 'name',
        'name_label': 'Specimen / Test Name (e.g. Whole Blood, Serum, Plasma, Bone Marrow, CSF, Pleural Fluid)',
        'description': 'Hematological and biochemical specimen types and laboratory panels.',
    },
    'pathology_specimen': {
        'title': 'Pathology Specimen Types',
        'icon': '🔬',
        'table_name': 'tblPathologySpecimenType',
        'model': PathologySpecimenType,
        'pk': 'id',
        'name_field': 'name',
        'name_label': 'Specimen Type (e.g. Core Biopsy, Excision Biopsy, Resection, Bone Marrow Aspirate, Trephine, FNAC)',
        'description': 'Histopathological biopsy specimens, resections, and cytology samples.',
    },
    'molecular_type': {
        'title': 'Molecular & Cytogenetic Tests',
        'icon': '🧬',
        'table_name': 'tblMolecularTestType',
        'model': MolecularTestType,
        'pk': 'id',
        'name_field': 'name',
        'name_label': 'Test Type (e.g. FISH, NGS Panel, RT-PCR, Karyotyping, Sanger Sequencing, IHC)',
        'description': 'Genomic, biomarker, cytogenetic, and translocation assay types.',
    },
}

def get_lookup_config(category):
    return LOOKUP_CONFIG.get(category, LOOKUP_CONFIG['purpose'])
