#!/usr/bin/env python
# coding: utf-8

# # SPARC Data Pipeline & Baryonic Valve Model Validation
# **Author:** Mounir Djebassi (DJEBASSI MOUNIR)  
# **Affiliation:** INAS - International Network of Algerian Scientists · Independent Researcher  
# **Location:** Constantine, Algeria  
# **Identifiers:** ORCID: [0009-0009-6871-7693](https://orcid.org/0009-0009-6871-7693) | GitHub: [djebassimounir-dev](https://github.com/djebassimounir-dev)  
# **Date:** October 2026  
# 
# ---
# 
# ## Abstract & Overview
# This notebook contains the complete, reproducible computational pipeline for analyzing 175 galaxy rotation curves from the **SPARC** (Spitzer Photometry and Accurate Rotation Curves) dataset. It evaluates the empirical performance of the **Baryonic Valve** phenomenological model ($V_{\text{eff}}^2$) and investigates its asymptotic divergence from the **Baryonic Tully-Fisher Relation (BTFR)**.
# 
# ### Model Equations
# 1. **Effective Velocity:**
#    $$V_{\text{eff}}^2(r) = V_{\text{bar}}^2(r) + B_0^2 \frac{\exp(-\eta(r))}{\eta(r)}$$
# 2. **Dimensionless Relaxation Parameter:**
#    $$\eta(r) = \frac{l(r)}{r} = \frac{l_0}{V_{\text{bar}}^2(r) \cdot r}$$
# 3. **Asymptotic Slope Derivation:**
#    $$\frac{d\ln V_{\text{flat}}}{d\ln M} = \frac{1+\eta}{2} \xrightarrow{\eta \ll 1} 0.50 \quad (\text{vs. BTFR observational requirement } \approx 0.25)$$
# 
# 

# In[1]:


import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Model parameters
L_0 = 36034.48       # Relaxation length scale (km^2/s^2 * kpc)
B_0_SQ = 1.00        # Propagator amplitude (km^2/s^2)
G_GRAV = 4.30091e-6  # Gravitational constant (kpc * (km/s)^2 / M_sun)

# Data directory configuration
DATA_DIR = r"C:\Users\LENOVO\Desktop\EDPZ_Work\Rotmod_LTG"

print(f"Configuration loaded. Target data path: {DATA_DIR}")



# ## 1. SPARC Data Loading & Parsing Pipeline
# We load `.dat` rotation curve files from the SPARC database. For each galaxy, the total Newtonian baryonic velocity squared is computed as:
# $$V_{\text{bar}}^2(r) = V_{\text{disk}}|V_{\text{disk}}| + V_{\text{gas}}|V_{\text{gas}}| + V_{\text{bulge}}|V_{\text{bulge}}|$$
# 
# 

# In[2]:


def analyze_sparc_catalog(data_dir):
    if not os.path.exists(data_dir):
        print(f"Warning: Directory {data_dir} not found locally. Running in demonstration mode.")
        return None, None
        
    dat_files = glob.glob(os.path.join(data_dir, "*.dat"))
    results = []
    excluded_count = 0

    for filepath in dat_files:
        filename = os.path.basename(filepath)
        galaxy_name = filename.split('_')[0]
        
        try:
            data = np.loadtxt(filepath, comments='#')
            if data.ndim != 2 or data.shape[0] < 3:
                excluded_count += 1
                continue
                
            r = data[:, 0]       # Radius (kpc)
            v_obs = data[:, 1]   # Observed velocity (km/s)
            err_v = data[:, 2]   # Error (km/s)
            v_gas = data[:, 3]   # Gas component
            v_disk = data[:, 4]  # Disk component
            v_bulge = data[:, 5] if data.shape[1] > 5 else np.zeros_like(r)
            
            # Baryonic velocity squared
            v_bar_sq = (v_disk * np.abs(v_disk)) + (v_gas * np.abs(v_gas)) + (v_bulge * np.abs(v_bulge))
            
            # Mask non-physical / zero error points
            valid_mask = (r > 0) & (v_bar_sq > 0) & (err_v > 0)
            if np.sum(valid_mask) < 3:
                excluded_count += 1
                continue
                
            r_v = r[valid_mask]
            v_obs_v = v_obs[valid_mask]
            err_v_v = err_v[valid_mask]
            v_bar_sq_v = v_bar_sq[valid_mask]
            
            # Model calculation
            l_r = L_0 / v_bar_sq_v
            eta = l_r / r_v
            
            corrective_term = np.zeros_like(eta)
            safe_eta = (eta > 1e-6) & (eta < 100.0)
            corrective_term[safe_eta] = B_0_SQ * np.exp(-eta[safe_eta]) / eta[safe_eta]
            
            v_eff_sq = v_bar_sq_v + corrective_term
            v_eff = np.sqrt(np.maximum(0, v_eff_sq))
            
            residuals = v_obs_v - v_eff
            galaxy_rmse = np.sqrt(np.mean(residuals**2))
            
            v_flat_est = v_eff[-1]
            m_bar_est = np.max(v_bar_sq_v) * r_v[-1] / G_GRAV
            
            results.append({
                'Galaxy': galaxy_name,
                'N_points': len(r_v),
                'RMSE': galaxy_rmse,
                'V_flat': v_flat_est,
                'M_bar_est': m_bar_est
            })
            
        except Exception:
            excluded_count += 1
            continue

    df_results = pd.DataFrame(results)
    return df_results, excluded_count

# Run analysis if local path exists
df_results, excluded = analyze_sparc_catalog(DATA_DIR)
if df_results is not None:
    print(f"Successfully processed {len(df_results)} galaxies.")
    print(f"Global RMSE: {np.sqrt(np.mean(df_results['RMSE']**2)):.2f} km/s")



# ## 2. Asymptotic Limitation Analysis & BTFR Test
# To rigorously evaluate the model's behavior at large radii ($r \to \infty$), we compute the analytical slope:
# $$\frac{d\ln V_{\text{flat}}}{d\ln M} = \frac{1+\eta}{2}$$
# Below, we simulate a synthetic population across SPARC mass scales ($10^8 - 10^{11.5} M_\odot$) to demonstrate the divergence between the theoretical asymptotic prediction and observational constraints.
# 
# 

# In[3]:


# Generate mass array for asymptotic evaluation
M_bar_array = np.logspace(8.0, 11.5, 100)
GM_array = G_GRAV * M_bar_array
eta_array = L_0 / GM_array

# Theoretical slope calculation
slope_predicted = (1.0 + eta_array) / 2.0

# Asymptotic flat velocity predicted by the model
v_flat_model_sq = B_0_SQ * np.exp(-eta_array) / eta_array
v_flat_model = np.sqrt(np.maximum(0, v_flat_model_sq))

# Observational reference slope (BTFR: V ~ M^0.25)
v_flat_btfr_ref = 50.0 * (M_bar_array / 1e10)**0.25

# Plotting the critical comparison
plt.figure(figsize=(9, 5.5))
plt.loglog(M_bar_array, v_flat_model, label='Baryonic Valve Asymptotic Model [(1+eta)/2]', color='crimson', linewidth=2.5)
plt.loglog(M_bar_array, v_flat_btfr_ref, label=r'BTFR Empirical Slope ($\propto M^{0.25}$)', color='navy', linestyle='--', linewidth=2)

plt.xlabel(r'Total Baryonic Mass $M_{	ext{bar}}$ ($M_\odot$)', fontsize=11)
plt.ylabel(r'Asymptotic Flat Velocity $V_{	ext{flat}}$ (km/s)', fontsize=11)
plt.title('Critical Asymptotic BTFR Confrontation', fontsize=12)
plt.grid(True, which="both", ls="--", alpha=0.4)
plt.legend(fontsize=11)
plt.tight_layout()

# Save figure locally
plt.savefig('btfr_asymptotic_confrontation.png', dpi=300)
print("BTFR confrontation plot generated successfully.")


