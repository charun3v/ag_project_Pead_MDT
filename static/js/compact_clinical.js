// Compact Clinical Interactive Utilities

document.addEventListener('DOMContentLoaded', function () {
  // 1. Live BSA & BMI Calculation
  const heightInput = document.getElementById('id_height');
  const weightInput = document.getElementById('id_weight');
  const bsaDisplay = document.getElementById('calc_bsa');
  const bmiDisplay = document.getElementById('calc_bmi');

  function updateVitals() {
    if (!heightInput || !weightInput) return;
    const h = parseFloat(heightInput.value);
    const w = parseFloat(weightInput.value);

    if (h > 0 && w > 0) {
      // Mosteller formula: sqrt((h * w) / 3600)
      const bsa = Math.sqrt((h * w) / 3600.0).toFixed(2);
      const h_m = h / 100.0;
      const bmi = (w / (h_m * h_m)).toFixed(1);

      if (bsaDisplay) bsaDisplay.textContent = bsa + ' m²';
      if (bmiDisplay) bmiDisplay.textContent = bmi + ' kg/m²';
    } else {
      if (bsaDisplay) bsaDisplay.textContent = '—';
      if (bmiDisplay) bmiDisplay.textContent = '—';
    }
  }

  if (heightInput && weightInput) {
    heightInput.addEventListener('input', updateVitals);
    weightInput.addEventListener('input', updateVitals);
    updateVitals();
  }

  // 2. Live Paediatric Age Calculation
  const dobInput = document.getElementById('id_dob');
  const ageDisplay = document.getElementById('calc_age');

  function calculatePaediatricAge(dobString) {
    if (!dobString) return '';
    const dob = new Date(dobString);
    const today = new Date();
    
    // Difference in days
    const diffTime = today - dob;
    const totalDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (totalDays < 0) return '(future date)';
    if (totalDays < 30) return `${totalDays} day${totalDays === 1 ? '' : 's'}`;

    let years = today.getFullYear() - dob.getFullYear();
    let m = today.getMonth() - dob.getMonth();
    if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
      years--;
    }

    let months = (today.getFullYear() - dob.getFullYear()) * 12 + (today.getMonth() - dob.getMonth());
    if (today.getDate() < dob.getDate()) {
      months--;
    }
    const remMonths = months % 12;

    if (years === 0) {
      return `${months} month${months === 1 ? '' : 's'}`;
    } else if (years < 5) {
      let str = `${years} yr${years === 1 ? '' : 's'}`;
      if (remMonths > 0) str += ` ${remMonths} mo`;
      return str;
    } else {
      return `${years} years`;
    }
  }

  if (dobInput && ageDisplay) {
    dobInput.addEventListener('change', function () {
      ageDisplay.textContent = calculatePaediatricAge(dobInput.value) || '—';
    });
    if (dobInput.value) {
      ageDisplay.textContent = calculatePaediatricAge(dobInput.value) || '—';
    }
  }

  // 3. Cascading State -> District Selection
  const stateSelect = document.getElementById('id_state');
  const districtSelect = document.getElementById('id_district');
  const countryInput = document.getElementById('id_country');

  if (stateSelect && districtSelect) {
    stateSelect.addEventListener('change', function () {
      const stateId = stateSelect.value;
      if (!stateId) {
        districtSelect.innerHTML = '<option value="">---------</option>';
        return;
      }

      fetch(`/api/districts/?state_id=${stateId}`)
        .then(response => response.json())
        .then(data => {
          let opts = '<option value="">---------</option>';
          data.districts.forEach(d => {
            opts += `<option value="${d.district_id}">${d.district_name}</option>`;
          });
          districtSelect.innerHTML = opts;
        })
        .catch(err => console.error('District fetch error:', err));
    });
  }

  // Country logic
  if (countryInput && stateSelect && districtSelect) {
    countryInput.addEventListener('input', function () {
      const val = countryInput.value.trim().toLowerCase();
      if (val !== 'india' && val !== '') {
        stateSelect.disabled = true;
        districtSelect.disabled = true;
      } else {
        stateSelect.disabled = false;
        districtSelect.disabled = false;
      }
    });
  }
});
