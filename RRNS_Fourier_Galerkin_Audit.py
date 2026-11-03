#!/usr/bin/env python
# coding: utf-8

# # Rapid rotation and cubic damping: a Fourier-Galerkin audit
# 
# **Companion notebook to the research framework PDF.** This notebook is designed to be run top-to-bottom in Python with NumPy, SciPy, and Matplotlib.
# 
# It performs three finite-dimensional checks:
# 
# 1. verifies the projected Coriolis spectrum, including the separate spatial-mean mode;
# 2. checks the Galerkin kinetic-energy balance numerically;
# 3. compares filtered solutions for decreasing Rossby numbers at one fixed Fourier cutoff.
# 
# **Scope:** this is a numerical audit of a fixed, finite Fourier-Galerkin model. It does not prove a PDE limit, a uniform-in-cutoff estimate, or a physical derivation of the cubic damping coefficient. The finest Rossby number is only a numerical proxy, not the exact averaged solution.

# ## 1. Model and conventions
# 
# We use the nondimensional, unforced periodic model
# 
# \[
# \partial_t u + \nu A u + B(u,u) + \varepsilon^{-1}Lu + \gamma C(u)=0,
# \qquad \nabla\cdot u=0,
# \]
# 
# with \(A=-\mathbb P\Delta\), \(B(u,u)=\mathbb P[(u\cdot\nabla)u]\), \(Lu=\mathbb P(e_3\times u)\), and \(C(u)=\mathbb P(|u|^2u)\). Fourier coefficients below use the normalized-series convention: the coefficient array is `fftn(field)/M**3`.
# 
# The cutoff retains the cube \(|k_j|\le K\). Products are evaluated on an oversampled grid with \(M>4K\), which prevents cubic products from aliasing back into the retained modes. This is a small demonstrator, not a production turbulence solver.

# In[1]:


import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp

np.set_printoptions(precision=6, suppress=True)

# Fixed Galerkin cutoff and oversampled physical grid.
M = 8
K = 1
nu = 0.08
gamma = 0.15
t_final = 0.10
assert M > 4*K, "Need M > 4K for the retained cubic interactions."

k1 = np.fft.fftfreq(M)*M
kx, ky, kz = np.meshgrid(k1, k1, k1, indexing="ij")
KV = np.stack([kx, ky, kz], axis=0)
k2 = np.sum(KV**2, axis=0)
keep = np.max(np.abs(KV), axis=0) <= K

x = 2*np.pi*np.arange(M)/M
X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
J = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 0.]])  # e3 cross .
e3 = np.array([0., 0., 1.])

def fft_series(field):
    """Normalized Fourier-series coefficients along the last 3 axes."""
    return np.fft.fftn(field, axes=(-3, -2, -1))/(M**3)

def ifft_series(coeff):
    """Physical grid values from normalized Fourier-series coefficients."""
    return np.fft.ifftn(coeff*(M**3), axes=(-3, -2, -1))

def project_solenoidal(coeff):
    """Apply the Fourier Leray projector; leave the spatial mean untouched."""
    out = np.array(coeff, dtype=np.complex128, copy=True)
    nonzero = k2 > 0
    dot = np.sum(KV*out, axis=0)
    out[:, nonzero] -= (KV[:, nonzero]*dot[nonzero]/k2[nonzero])
    out[:, ~keep] = 0
    return out

def coriolis_hat(coeff):
    """L=P(e3 x .), applied mode-by-mode to retained coefficients."""
    cross = np.zeros_like(coeff)
    cross[0] = -coeff[1]
    cross[1] = coeff[0]
    return project_solenoidal(cross)

def make_initial_data():
    # Divergence-free because each component is independent of its own coordinate.
    u = np.stack([np.sin(Y), np.sin(Z), np.sin(X)], axis=0)
    return project_solenoidal(fft_series(u))

U0 = make_initial_data()
print("retained Fourier modes:", int(np.sum(keep)))
print("initial mean kinetic energy:", 0.5*np.sum(np.abs(U0)**2))


# ## 2. Coriolis spectrum and slow modes
# 
# For a nonzero wavevector \(k\), the restriction of \(P_k(e_3\times\cdot)\) to \(k^\perp\) has eigenvalues \(0,\pm i k_3/|k|\) on the full three-component Fourier fiber (the zero eigenvalue is the longitudinal direction before restricting; on the solenoidal fiber the two branches are \(\pm i k_3/|k|\)). When \(k_3=0\), the entire solenoidal fiber is in the kernel. At \(k=0\), the mean horizontal components rotate with eigenvalues \(\pm i\), while the vertical mean is stationary.
# 
# Thus the slow subspace is 2D-3C: fields are independent of \(x_3\), and may still have three components, together with the vertical mean. Horizontal mean velocity is not slow.

# In[2]:


def coriolis_matrix(k):
    """3x3 symbol P_k J; at k=0 the projector is the identity."""
    k = np.asarray(k, dtype=float)
    kk = float(k @ k)
    Pk = np.eye(3) if kk == 0 else np.eye(3) - np.outer(k, k)/kk
    return Pk @ J

for k in (np.array([1., 1., 1.]), np.array([1., 0., 0.]), np.array([0., 0., 0.])):
    eig = np.linalg.eigvals(coriolis_matrix(k))
    print(f"k={k.astype(int)}  eigenvalues={np.sort_complex(eig)}")

# For k=(1,1,1), the nonzero branches should be +/- i/sqrt(3).
# Compare real and imaginary parts separately: sorting complex values can be
# unstable when roundoff gives the nominally-zero real parts tiny +/- errors.
expected = np.array([0j, 1j/np.sqrt(3), -1j/np.sqrt(3)])
actual = np.linalg.eigvals(coriolis_matrix([1, 1, 1]))
assert np.max(np.abs(actual.real)) < 1e-12
assert np.allclose(np.sort(actual.imag), np.sort(expected.imag), atol=1e-12, rtol=0)

# The horizontal mean rotates; the vertical mean is in ker(L).
Lmean = coriolis_matrix([0, 0, 0])
print("mean-mode kernel dimension:", int(np.sum(np.abs(np.linalg.eigvals(Lmean)) < 1e-12)))


# ## 3. Resonance bookkeeping
# 
# In a helical eigenbasis, each nonzero wavevector has a branch index \(\sigma\in\{-1,+1\}\) and frequency \(\omega_{k,\sigma}=\sigma k_3/|k|\). The quadratic resonance condition is
# 
# \[
# k=m+n,\qquad \omega_{k,\sigma_k}=\omega_{m,\sigma_m}+\omega_{n,\sigma_n}.
# \]
# 
# For cubic damping the four-mode condition is \(k=l+m+n\) and \(\omega_{k,\sigma_k}=\omega_{l,\sigma_l}+\omega_{m,\sigma_m}+\omega_{n,\sigma_n}\). Zero-frequency modes and \(k=0\) use their separately defined eigenfrequencies. Phase matching identifies candidates; the vector interaction coefficient may still vanish.

# In[3]:


def branch_frequency(k, sigma):
    """Frequency for k!=0 and sigma=+/-1; handle k=0 separately."""
    k = np.asarray(k, dtype=float)
    if np.all(k == 0):
        raise ValueError("At k=0 use mean-mode branches: -1, 0, +1.")
    return sigma*k[2]/np.linalg.norm(k)

# A simple exact resonance involving only slow (k3=0) modes.
k, m, n = np.array([1, 0, 0]), np.array([0, 1, 0]), np.array([1, -1, 0])
assert np.array_equal(k, m+n)
residual = branch_frequency(k, +1)-branch_frequency(m, -1)-branch_frequency(n, +1)
print("slow-mode triad resonance residual:", residual)


# ## 4. Dealiased Fourier-Galerkin dynamics
# 
# The finite-dimensional solver below evaluates advection and cubic damping on the oversampled grid, transforms back, projects onto divergence-free modes, and truncates. The Coriolis term is kept in the original equation. The energy check compares the computed kinetic-energy derivative with the exact Galerkin dissipation identity.

# In[4]:


def rhs_hat(U, epsilon):
    """Right-hand side of the dealiased finite Galerkin ODE in Fourier space."""
    U = np.asarray(U).reshape(3, M, M, M).copy()
    U[:, ~keep] = 0

    u = ifft_series(U).real
    grad_u = np.empty((3, 3, M, M, M), dtype=float)  # component, derivative, x,y,z
    for j in range(3):
        dU = 1j*KV[j]*U
        grad_u[:, j] = ifft_series(dU).real

    adv = np.zeros_like(u)
    for j in range(3):
        adv += u[j][None, ...]*grad_u[:, j]
    adv_hat = project_solenoidal(fft_series(adv))

    damp = np.sum(u*u, axis=0, keepdims=True)*u
    damp_hat = project_solenoidal(fft_series(damp))

    visc_hat = nu*k2[None, ...]*U
    rot_hat = coriolis_hat(U)/epsilon
    out = -visc_hat - adv_hat - rot_hat - gamma*damp_hat
    out[:, ~keep] = 0
    return out

# Check the kinetic-energy derivative at the initial condition.
R0 = rhs_hat(U0, epsilon=0.1)
energy_rate_numeric = float(np.real(np.vdot(U0, R0)))
u0 = ifft_series(U0).real
energy_rate_expected = float(-nu*np.sum(k2*np.abs(U0)**2)
                             -gamma*np.mean(np.sum(u0*u0, axis=0)**2))
print("energy derivative, numerical:", energy_rate_numeric)
print("energy derivative, identity: ", energy_rate_expected)
print("absolute closure residual:     ", abs(energy_rate_numeric-energy_rate_expected))


# ## 5. Filtered convergence experiment at fixed cutoff
# 
# For each Rossby number, integrate the original Galerkin system and filter the final state by \(v_N^\varepsilon(t)=\exp(tL_N/\varepsilon)u_N^\varepsilon(t)\). Compare successive filtered states. This is only an exploratory finite-cutoff diagnostic: the finest run is not the exact averaged solution, and the experiment cannot establish the PDE limit or uniformity as \(K\to\infty\).

# In[5]:


def filter_state(U, t, epsilon):
    V = np.zeros_like(U)
    for idx in zip(*np.where(keep)):
        k = np.array([kx[idx], ky[idx], kz[idx]], dtype=float)
        Lk = coriolis_matrix(k)
        # exp(t L_k/epsilon) acts on the three-component Fourier coefficient.
        vals, vecs = np.linalg.eig(Lk)
        expL = vecs @ np.diag(np.exp((t/epsilon)*vals)) @ np.linalg.inv(vecs)
        V[(slice(None),)+idx] = expL @ U[(slice(None),)+idx]
    return V

def solve_one(epsilon):
    # Resolve fast rotation with a conservative maximum step.
    sol = solve_ivp(lambda t,y: rhs_hat(y, epsilon).ravel(),
                    (0.0, t_final), U0.ravel().astype(np.complex128),
                    method="DOP853", rtol=2e-8, atol=2e-10,
                    max_step=epsilon/12)
    if not sol.success:
        raise RuntimeError(sol.message)
    Ufinal = sol.y[:, -1].reshape(3, M, M, M)
    return filter_state(Ufinal, t_final, epsilon), sol.nfev

epsilons = [0.12, 0.06, 0.03, 0.015]
filtered = {}
work = {}
for eps in epsilons:
    filtered[eps], work[eps] = solve_one(eps)
    print(f"epsilon={eps:7.4f}  RHS evaluations={work[eps]:5d}  "
          f"filtered energy={0.5*np.sum(np.abs(filtered[eps])**2):.8f}")

errors = []
for e_coarse, e_fine in zip(epsilons[:-1], epsilons[1:]):
    err = np.sqrt(np.sum(np.abs(filtered[e_coarse]-filtered[e_fine])**2))
    errors.append(err)
    print(f"||v({e_coarse})-v({e_fine})||_2 = {err:.6e}")

rates = [np.log(errors[j]/errors[j+1])/np.log(2) for j in range(len(errors)-1)]
print("exploratory successive-difference slopes:", rates)
plt.loglog(epsilons[:-1], errors, "o-", label="successive filtered differences")
plt.xlabel("coarser Rossby number")
plt.ylabel("Fourier L2 difference")
plt.title("Fixed-cutoff averaging diagnostic (not a PDE proof)")
plt.grid(True, which="both", alpha=0.3)
plt.legend();
plt.show()


# ## 6. Reading the output and next steps
# 
# - The spectrum check is algebraic and should reproduce the two wave branches and the mean-mode exception.
# - The energy residual should be close to floating-point and time-independent evaluation error; it is not a time-integration conservation claim because viscosity and damping dissipate energy.
# - Successive filtered differences are a practical diagnostic only. They are not errors against the exact resonant limit and should not be reported as a convergence rate without a separately computed averaged solution and a time-step study.
# - The averaging theorem in the companion article is for fixed Fourier cutoff. The major analytical problem is to control its constants and remainders uniformly as the cutoff grows.
# - The cubic coefficient gamma has dimensions T/L^2 in dimensional variables. A numerical fit cannot supply a constitutive derivation; the physical mechanism and validation data must be specified independently.
