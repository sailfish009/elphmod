#!/usr/bin/env python3

# Copyright (C) 2021 elphmod Developers
# This program is free software under the terms of the GNU GPLv3 or later.

from __future__ import division

import numpy as np

from . import MPI, occupations
comm = MPI.comm
info = MPI.info

def susceptibility(e, kT=0.025, eta=1e-10, occupations=occupations.fermi_dirac):
    r"""Calculate real part of static electronic susceptibility.

    .. math::

        \chi_{\vec q} = \frac 2 N \sum_{\vec k} \frac
            {f(\epsilon_{\vec k + \vec q}) - f(\epsilon_{\vec k})}
            {\epsilon_{\vec k + \vec q} - \epsilon_{\vec k} + \I \eta}

    The resolution in q is limited by the resolution in k.

    Parameters
    ----------
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    kT : float
        Smearing temperature.
    eta : float
        Absolute value of "infinitesimal" imaginary number in denominator.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.

    Returns
    -------
    function
        Static electronic susceptibility as a function of :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    """
    nk, nk = e.shape

    x = e / kT

    f = occupations(x)
    d = occupations.delta(x).sum() / kT

    e = np.tile(e, (2, 2))
    f = np.tile(f, (2, 2))

    scale = nk / (2 * np.pi)
    eta2 = eta ** 2
    prefactor = 2.0 / nk ** 2

    def calculate_susceptibility(q1=0, q2=0):
        q1 = int(round(q1 * scale)) % nk
        q2 = int(round(q2 * scale)) % nk

        if q1 == q2 == 0:
            return -prefactor * d

        df = f[q1:q1 + nk, q2:q2 + nk] - f[:nk, :nk]
        de = e[q1:q1 + nk, q2:q2 + nk] - e[:nk, :nk]

        return prefactor * np.sum(df * de / (de * de + eta2))

    return calculate_susceptibility

def susceptibility2(e, kT=0.025, nmats=1000, hyb_width=1.0, hyb_height=0.0):
    r"""Calculate the Lindhardt bubble using the Green's functions explicitly.

    .. math::

        \chi = \frac \beta 4 - \frac 1 \beta
            \sum_n G(\nu_n) - \frac 1 {(\I \nu_n)^2}

    Only omega = 0 (static) calculation is performed.

    For the treatment of the :math:`1 / \I \nu_n` tail, see:

        Appendix B of the thesis of Hartmut Hafermann.

    Multiply by 2 for spin.

    The resolution in q is limited by the resolution in k.

    Original implementation by Erik G.C.P. van Loon.

    Parameters
    ----------
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    kT : float
        Smearing temperature.
    nmats : int
        Number of fermionic Matsubara frequencies.
    hyb_width : float
        Width of box-shaped hybridization function.
    hyb_height : float
        Height of box-shaped hybridization function.

    Returns
    -------
    function
        Static electronic susceptibility as a function of :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    """
    nk, nk = e.shape

    e = np.tile(e, (2, 2))

    scale = nk / (2 * np.pi)

    prefactor = kT * 4.0 / nk ** 2
    # factor 2 for the negative Matsubara frequencies
    # factor 2 for the spin

    nu = (2 * np.arange(nmats) + 1) * np.pi * kT # Matsubara frequencies

    Delta = -2j * hyb_height * np.arctan(2 * hyb_width / nu) # hybridization

    G = np.empty((nmats, 2 * nk, 2 * nk), dtype=complex) # Green's functions

    for i in range(nmats):
        G[i] = 1.0 / (1j * nu[i] - e - Delta[i])

    tail = -2.0 / (4 * kT) + prefactor * nk ** 2 * np.sum(1.0 / nu ** 2)
    # see Appendix B of the thesis of Hartmut Hafermann
    # factor 2 for spin
    # VERIFY THAT THIS IS CORRECT! (after rewriting function)

    def calculate_susceptibility(q1=0, q2=0):
        q1 = int(round(q1 * scale)) % nk
        q2 = int(round(q2 * scale)) % nk

        Gk  = G[:, :nk, :nk]
        Gkq = G[:, q1:q1 + nk, q2:q2 + nk]

        return prefactor * np.sum(Gk * Gkq) + tail

    return calculate_susceptibility

def polarization(e, U, kT=0.025, eps=1e-15, subspace=None,
        occupations=occupations.fermi_dirac):
    r"""Calculate RPA polarization in orbital basis (density-density).

    .. math::

        \Pi_{\vec q \alpha \beta} = \frac 2 N \sum_{\vec k m n}
            \bracket{\vec k + \vec q \alpha}{\vec k + \vec q m}
            \bracket{\vec k n}{\vec k \alpha}
            \frac
                {f(\epsilon_{\vec k + \vec q m}) - f(\epsilon_{\vec k n})}
                {\epsilon_{\vec k + \vec q m} - \epsilon_{\vec k n}}
            \bracket{\vec k + \vec q m}{\vec k + \vec q \beta}
            \bracket{\vec k \beta}{\vec k n}

    The resolution in q is limited by the resolution in k.

    If `subspace` is given, a cRPA calculation is performed. `subspace` must be
    a boolean array with the same shape as `e`, where ``True`` marks states of
    the target subspace, interactions between which are excluded.

    Parameters
    ----------
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    U : ndarray
        Coefficients for transform to orbital basis. These are given by the
        eigenvectors of the Wannier Hamiltonian.
    kT : float
        Smearing temperature.
    eps : float
        Smallest allowed absolute value of divisor.
    subspace : ndarray or None
        Boolean array to select k points and/or bands in cRPA target subspace.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.

    Returns
    -------
    function
        RPA polarization in orbital basis as a function of :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    """
    cRPA = subspace is not None

    if e.ndim == 2:
        e = e[:, :, np.newaxis]

    if U.ndim == 3:
        U = U[:, :, :, np.newaxis]

    if cRPA and subspace.shape != e.shape:
        subspace = np.reshape(subspace, e.shape)

    nk, nk, nb = e.shape
    nk, nk, no, nb = U.shape # U[k1, k2, a, n] = <k a|k n>

    x = e / kT

    f = occupations(x)
    d = occupations.delta(x) / (-kT)

    e = np.tile(e, (2, 2, 1))
    f = np.tile(f, (2, 2, 1))
    U = np.tile(U, (2, 2, 1, 1))

    if cRPA:
        subspace = np.tile(subspace, (2, 2, 1))

    scale = nk / (2 * np.pi)
    prefactor = 2.0 / nk ** 2

    k1 = slice(0, nk)
    k2 = k1

    dfde = np.empty((nk, nk))

    def calculate_polarization(q1=0, q2=0):
        q1 = int(round(q1 * scale)) % nk
        q2 = int(round(q2 * scale)) % nk

        kq1 = slice(q1, q1 + nk)
        kq2 = slice(q2, q2 + nk)

        Pi = np.empty((nb, nb, no, no), dtype=complex)

        for m in range(nb):
            for n in range(nb):
                df = f[kq1, kq2, m] - f[k1, k2, n]
                de = e[kq1, kq2, m] - e[k1, k2, n]

                ok = abs(de) > eps

                dfde[ ok] = df[ok] / de[ok]
                dfde[~ok] = d[:, :, n][~ok]

                if cRPA:
                    exclude = np.where(
                        subspace[kq1, kq2, m] & subspace[k1, k2, n])

                    dfde[exclude] = 0.0

                UU = U[kq1, kq2, :, m].conj() * U[k1, k2, :, n]

                Pi[m, n] = np.einsum('kla,kl,klb->ab', UU.conj(), dfde, UU)

        return prefactor * Pi.sum(axis=(0, 1))

    return calculate_polarization

def phonon_self_energy(q, e, g2=None, kT=0.025, eps=1e-15,
        occupations=occupations.fermi_dirac, fluctuations=False, Delta=None,
        Delta_diff=False, Delta_occupations=occupations.gauss, Delta_kT=0.025,
        comm=comm):
    r"""Calculate phonon self-energy.

    .. math::

        \Pi_{\vec q \nu} = \frac 2 N \sum_{\vec k m n}
            |g_{\vec q \nu \vec k m n}|^2 \frac
                {f(\epsilon_{\vec k + \vec q m}) - f(\epsilon_{\vec k n})}
                {\epsilon_{\vec k + \vec q m} - \epsilon_{\vec k n}}

    Parameters
    ----------
    q : list of 2-tuples
        Considered q points defined via crystal coordinates :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g2 : ndarray
        Squared electron-phonon coupling.
    kT : float
        Smearing temperature.
    eps : float
        Smallest allowed absolute value of divisor.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.
    fluctuations : bool
        Return integrand too (for fluctuation analysis)?
    Delta : float
        Half the width of energy window around Fermi level to be excluded.
    Delta_diff : bool
        Calculate derivative of phonon self-energy w.r.t. `Delta`?
    Delta_occupations : function
        Smoothened Heaviside function to realize excluded energy window.
    Delta_kT : float
        Temperature to smoothen Heaviside function.

    Returns
    -------
    ndarray
        Phonon self-energy.
    """
    nQ = len(q)
    nk = e.shape[0]

    e = np.reshape(e, (nk, nk, -1))
    nbnd = e.shape[-1]

    if g2 is None:
        g2 = np.ones((nQ, 1))

    else:
        g2 = np.reshape(g2, (nQ, -1, nk, nk, nbnd, nbnd))

    nb = g2.shape[1]

    x = e / kT

    f = occupations(x)
    d = occupations.delta(x) / (-kT)

    if Delta is not None:
        x1 = ( e - Delta) / Delta_kT
        x2 = (-e - Delta) / Delta_kT

        Theta = 2 - Delta_occupations(x1) - Delta_occupations(x2)

        if Delta_diff:
            delta = Delta_occupations.delta(x1) + Delta_occupations.delta(x2)
            delta /= -Delta_kT

    e = np.tile(e, (2, 2, 1))
    f = np.tile(f, (2, 2, 1))

    if Delta is not None:
        Theta = np.tile(Theta, (2, 2, 1))

        if Delta_diff:
            delta = np.tile(delta, (2, 2, 1))

    scale = nk / (2 * np.pi)
    prefactor = 2.0 / nk ** 2

    sizes, bounds = MPI.distribute(nQ, bounds=True, comm=comm)

    my_Pi = np.empty((sizes[comm.rank], nb), dtype=g2.dtype)

    if fluctuations:
        my_Pi_k = np.empty((sizes[comm.rank], nb, nk, nk, nbnd, nbnd),
            dtype=g2.dtype)

    dfde = np.empty((nk, nk, nbnd, nbnd))

    k1 = slice(0, nk)
    k2 = slice(0, nk)

    for my_iq, iq in enumerate(range(*bounds[comm.rank:comm.rank + 2])):
        q1 = int(round(q[iq, 0] * scale)) % nk
        q2 = int(round(q[iq, 1] * scale)) % nk

        kq1 = slice(q1, q1 + nk)
        kq2 = slice(q2, q2 + nk)

        for m in range(nbnd):
            for n in range(nbnd):
                df = f[kq1, kq2, m] - f[k1, k2, n]
                de = e[kq1, kq2, m] - e[k1, k2, n]

                ok = abs(de) > eps

                dfde[:, :, m, n][ ok] = df[ok] / de[ok]
                dfde[:, :, m, n][~ok] = d[:, :, n][~ok]

                if Delta is not None:
                    if Delta_diff:
                        envelope = (
                              Theta[kq1, kq2, m] * delta[k1, k2, n]
                            + delta[kq1, kq2, m] * Theta[k1, k2, n]
                            )
                    else:
                        envelope = Theta[kq1, kq2, m] * Theta[k1, k2, n]

                    dfde[:, :, m, n] *= envelope

        for nu in range(nb):
            Pi_k = g2[iq, nu] * dfde

            my_Pi[my_iq, nu] = prefactor * Pi_k.sum()

            if fluctuations:
                my_Pi_k[my_iq, nu] = 2 * Pi_k

    Pi = np.empty((nQ, nb), dtype=g2.dtype)

    comm.Allgatherv(my_Pi, (Pi, sizes * nb))

    if fluctuations:
        Pi_k = np.empty((nQ, nb, nk, nk, nbnd, nbnd), dtype=g2.dtype)

        comm.Allgatherv(my_Pi_k, (Pi_k, sizes * nb * nk * nk * nbnd * nbnd))

        return Pi, Pi_k

    else:
        return Pi

def phonon_self_energy2(q, e, g2, kT=0.025, nmats=1000, hyb_width=1.0,
        hyb_height=0.0, GB=4.0):
    """Calculate phonon self-energy using the Green's functions explicitly.

    Parameters
    ----------
    q : list of 2-tuples
        Considered q points defined via crystal coordinates :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g2 : ndarray
        Squared electron-phonon coupling.
    kT : float
        Smearing temperature.
    nmats : int
        Number of fermionic Matsubara frequencies.
    hyb_width : float
        Width of box-shaped hybridization function.
    hyb_height : float
        Height of box-shaped hybridization function.
    GB : float
        Memory limit in gigabytes. Exit if exceeded.

    Returns
    -------
    ndarray
        Phonon self-energy.

    See Also
    --------
    susceptibility2 : Similar function with `g2` set to one.
    """
    nk, nk = e.shape
    nQ, nb, nk, nk = g2.shape

    if nmats * (2 * nk) ** 2 * np.dtype(complex).itemsize * comm.size > GB * 1e9:
        info("Error: Memory limit (%g GB) exceeded!" % GB)
        quit()

    e = np.tile(e, (2, 2))

    scale = nk / (2 * np.pi)
    prefactor = kT * 4.0 / nk ** 2

    nu = (2 * np.arange(nmats) + 1) * np.pi * kT # Matsubara frequencies

    Delta = -2j * hyb_height * np.arctan(2 * hyb_width / nu) # hybridization

    G = np.empty((nmats, 2 * nk, 2 * nk), dtype=complex) # Green's functions

    for i in range(nmats):
        G[i] = 1.0 / (1j * nu[i] - e - Delta[i])

    tail = -2.0 / (4 * kT) / nk ** 2 + prefactor * np.sum(1.0 / nu ** 2)
    # VERIFY THAT THIS IS CORRECT!

    sizes, bounds = MPI.distribute(nQ, bounds=True)

    my_Pi = np.empty((sizes[comm.rank], nb), dtype=complex)

    for my_iq, iq in enumerate(range(*bounds[comm.rank:comm.rank + 2])):
        q1 = int(round(q[iq, 0] * scale)) % nk
        q2 = int(round(q[iq, 1] * scale)) % nk

        Gk  = G[:, :nk, :nk]
        Gkq = G[:, q1:q1 + nk, q2:q2 + nk]

        chi = prefactor * np.sum(Gk * Gkq, axis=0).real + tail

        for nu in range(nb):
            my_Pi[my_iq, nu] = np.sum(g2[iq, nu] * chi)

    Pi = np.empty((nQ, nb), dtype=complex)

    comm.Allgatherv(my_Pi, (Pi, sizes * nb))

    return Pi

def renormalize_coupling_band(q, e, g, W, U, kT=0.025, eps=1e-15,
        occupations=occupations.fermi_dirac, nbnd_sub=None, status=True):
    r"""Calculate renormalized electron-phonon coupling in band basis.

    .. math::

        \tilde g_{\vec q \nu \vec k m n} = g_{\vec q \nu \vec k m n}
            + \frac 2 N \sum_{\vec k' m' n' \alpha \beta \gamma \delta}
            U_{\vec k + \vec q \alpha m}^* U_{\vec k \beta n}
            W_{\vec q \alpha \beta \gamma \delta}
            U_{\vec k' + \vec q \gamma m'} U_{\vec k' \delta n'}^*
            \frac
                {f(\epsilon_{\vec k' + \vec q m'}) - f(\epsilon_{\vec k' n'})}
                {\epsilon_{\vec k' + \vec q m'} - \epsilon_{\vec k' n'}}
            g_{\vec q \nu \vec k' m' n'}

    Parameters
    ----------
    q : list of 2-tuples
        Considered q points defined via crystal coordinates :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g : ndarray
        Bare electron-phonon coupling in band basis.
    W : ndarray
        Dressed q-dependent Coulomb interaction in orbital basis.
    U : ndarray
        Eigenvectors of Wannier Hamiltonian belonging to considered bands.
    kT : float
        Smearing temperature.
    eps : float
        Smallest allowed absolute value of divisor.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.
    nbnd_sub : int
        Number of bands for Lindhard bubble. Defaults to all bands.
    status : bool
        Print status messages during the calculation?

    Returns
    -------
    ndarray
        Dressed electron-phonon coupling in band basis.

    See Also
    --------
    renormalize_coupling_orbital
    """
    nk, nk, nbnd = e.shape
    nQ, nmodes, nk, nk, nbnd, nbnd = g.shape

    dd = W.ndim == 3

    if dd:
        nQ, norb, norb = W.shape
    else:
        nQ, norb, norb, norb, norb = W.shape

    nk, nk, norb, nbnd = U.shape

    if nbnd_sub is None:
        nbnd_sub = nbnd

    x = e / kT

    f = occupations(x)
    d = occupations.delta(x) / (-kT)

    e = np.tile(e, (2, 2, 1))
    f = np.tile(f, (2, 2, 1))
    U = np.tile(U, (2, 2, 1, 1))

    scale = nk / (2 * np.pi)
    prefactor = 2.0 / nk ** 2

    sizes, bounds = MPI.distribute(nQ, bounds=True)

    my_g_ = np.empty((sizes[comm.rank], nmodes, nk, nk, nbnd, nbnd),
        dtype=complex)

    dfde = np.empty((nk, nk, nbnd_sub, nbnd_sub))

    for my_iq, iq in enumerate(range(*bounds[comm.rank:comm.rank + 2])):
        if status:
            print('Renormalize coupling for q point %d..' % (iq + 1))

        q1 = int(round(q[iq, 0] * scale)) % nk
        q2 = int(round(q[iq, 1] * scale)) % nk

        k1 = slice(0, nk)
        k2 = slice(0, nk)

        kq1 = slice(q1, q1 + nk)
        kq2 = slice(q2, q2 + nk)

        for m in range(nbnd_sub):
            for n in range(nbnd_sub):
                df = f[kq1, kq2, m] - f[k1, k2, n]
                de = e[kq1, kq2, m] - e[k1, k2, n]

                ok = abs(de) > eps

                dfde[:, :, m, n][ ok] = df[ok] / de[ok]
                dfde[:, :, m, n][~ok] = d[:, :, n][~ok]

        if dd:
            indices = 'KLcM,KLcN,KLMN,xKLMN->xc'
        else:
            indices = 'KLcM,KLdN,KLMN,xKLMN->xcd'

        Pig = prefactor * np.einsum(indices,
            U[kq1, kq2, :, :nbnd_sub], U[k1, k2, :, :nbnd_sub].conj(),
            dfde, g[iq, :, :, :, :nbnd_sub, :nbnd_sub])

        if dd:
            indices = 'klam,klan,ac,xc->xklmn'
        else:
            indices = 'klam,klbn,abcd,xcd->xklmn'

        my_g_[my_iq] = g[iq] + np.einsum(indices,
            U[kq1, kq2].conj(), U[k1, k2], W[iq], Pig)

        #   k+q m           K+q M
        #  ___/___ a     c ___/___
        #     \   \       /   \   \   x q
        #          :::::::         o~~~~~~~
        #  ___\___/       \___\___/
        #     /    b     d    /
        #    k n             K N

    g_ = np.empty((nQ, nmodes, nk, nk, nbnd, nbnd), dtype=complex)

    comm.Allgatherv(my_g_, (g_, sizes * nmodes * nk * nk * nbnd * nbnd))

    return g_

def renormalize_coupling_orbital(q, e, g, W, U, **kwargs):
    r"""Calculate renormalized electron-phonon coupling in orbital basis.

    .. math::

        \tilde g_{\vec q \nu \vec k \alpha \beta} = g_{\vec q \nu \vec k \alpha \beta}
            + \frac 2 N \sum_{\vec k m n \alpha' \beta' \gamma \delta}
            W_{\vec q \alpha \beta \gamma \delta}
            U_{\vec k + \vec q \gamma m} U_{\vec k \delta n}^*
            \frac
                {f(\epsilon_{\vec k + \vec q m}) - f(\epsilon_{\vec k n})}
                {\epsilon_{\vec k + \vec q m} - \epsilon_{\vec k n}}
            U_{\vec k + \vec q \alpha' m}^* U_{\vec k \beta' n}
            g_{\vec q \nu \vec k \alpha' \beta'}

    Parameters
    ----------
    q : list of 2-tuples
        Considered q points defined via crystal coordinates :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g : ndarray
        Bare electron-phonon coupling in orbital basis.
    W : ndarray
        Dressed q-dependent Coulomb interaction in orbital basis.
    U : ndarray
        Eigenvectors of Wannier Hamiltonian belonging to considered bands.
    **kwargs
        Parameters passed to :func:`Pi_g`.

    Returns
    -------
    ndarray
        Dressed electron-phonon coupling in orbital basis.

    See Also
    --------
    Pi_g
    renormalize_coupling_orbital
    """
    dd = W.ndim == 3

    if dd:
        indices = 'qac,qxc->qxa'
    else:
        indices = 'qabcd,qxcd->qxab'

    dg = np.einsum(indices, W, Pi_g(q, e, g, U, dd=dd, **kwargs))

    #            k+q m
    #   a     c ___/___ a'
    #  \   q   /   \   \   x q
    #   :::::::         o~~~~~~~
    #  /       \___\___/
    #   b     d    /    b'
    #             k n

    G = g.copy()

    for k1 in range(G.shape[2]):
        for k2 in range(G.shape[3]):
            if dd:
                for a in range(G.shape[4]):
                    G[:, :, k1, k2, a, a] += dg[:, :, a]
            else:
                G[:, :, k1, k2, :, :] += dg

    return G

def Pi_g(q, e, g, U, kT=0.025, eps=1e-15,
        occupations=occupations.fermi_dirac, dd=True, status=True):
    """Join electron-phonon coupling and Lindhard bubble in orbital basis.

    Parameters
    ----------
    q : list of 2-tuples
        Considered q points defined via crystal coordinates :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g : ndarray
        Bare electron-phonon coupling in orbital basis.
    U : ndarray
        Eigenvectors of Wannier Hamiltonian belonging to considered bands.
    kT : float
        Smearing temperature.
    eps : float
        Smallest allowed absolute value of divisor.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.
    dd : bool
        Consider only density-density terms?
    status : bool
        Print status messages during the calculation?

    Returns
    -------
    ndarray
        (k-independent) product of electron-phonon coupling and Lindhard bubble.
    """
    nk, nk, nbnd = e.shape
    nQ, nmodes, nk, nk, norb, norb = g.shape
    nk, nk, norb, nbnd = U.shape

    x = e / kT

    f = occupations(x)
    d = occupations.delta(x) / (-kT)

    e = np.tile(e, (2, 2, 1))
    f = np.tile(f, (2, 2, 1))
    U = np.tile(U, (2, 2, 1, 1))

    scale = nk / (2 * np.pi)
    prefactor = 2.0 / nk ** 2

    sizes, bounds = MPI.distribute(nQ, bounds=True)

    if dd:
        my_Pig = np.empty((sizes[comm.rank], nmodes, norb), dtype=complex)
    else:
        my_Pig = np.empty((sizes[comm.rank], nmodes, norb, norb), dtype=complex)

    dfde = np.empty((nk, nk, nbnd, nbnd))

    for my_iq, iq in enumerate(range(*bounds[comm.rank:comm.rank + 2])):
        if status:
            print('Calculate "g Pi" for q point %d..' % (iq + 1))

        q1 = int(round(q[iq, 0] * scale)) % nk
        q2 = int(round(q[iq, 1] * scale)) % nk

        k1 = slice(0, nk)
        k2 = slice(0, nk)

        kq1 = slice(q1, q1 + nk)
        kq2 = slice(q2, q2 + nk)

        for m in range(nbnd):
            for n in range(nbnd):
                df = f[kq1, kq2, m] - f[k1, k2, n]
                de = e[kq1, kq2, m] - e[k1, k2, n]

                ok = abs(de) > eps

                dfde[:, :, m, n][ ok] = df[ok] / de[ok]
                dfde[:, :, m, n][~ok] = d[:, :, n][~ok]

        if dd:
            indices = 'klcm,klcn,klmn,klam,klbn,xklab->xc'
        else:
            indices = 'klcm,kldn,klmn,klam,klbn,xklab->xcd'

        my_Pig[my_iq] = prefactor * np.einsum(indices,
            U[kq1, kq2], U[k1, k2].conj(), dfde, U[kq1, kq2].conj(), U[k1, k2],
            g[iq])

        #     k+q m
        #  c ___/___ a
        #       \   \   x q
        #            o~~~~~~~
        #    ___\___/
        #  d    /    b
        #      k n

    if dd:
        Pig = np.empty((nQ, nmodes, norb), dtype=complex)
        comm.Allgatherv(my_Pig, (Pig, sizes * nmodes * norb))
    else:
        Pig = np.empty((nQ, nmodes, norb, norb), dtype=complex)
        comm.Allgatherv(my_Pig, (Pig, sizes * nmodes * norb * norb))

    return Pig

def double_fermi_surface_average(q, e, g2, kT=0.025,
        occupations=occupations.fermi_dirac, comm=comm):
    """Calculate double Fermi-surface average.

    Parameters
    ----------
    q : list of 2-tuples
        Considered q points defined via crystal coordinates :math:`q_1, q_2 \in
        [0, 2 \pi)`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g2 : ndarray
        Quantity to be averaged, typically electron-phonon coupling.
    kT : float
        Smearing temperature.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.

    Returns
    -------
    float
        Double Fermi-surface average.
    """
    nk, nk, nel = e.shape
    nQ, nph = g2.shape[:2]

    d = occupations.delta(e / kT) / kT

    e = np.tile(e, (2, 2, 1))
    d = np.tile(d, (2, 2, 1))

    scale = nk / (2 * np.pi)

    sizes, bounds = MPI.distribute(nQ, bounds=True, comm=comm)

    my_av = np.empty((sizes[comm.rank], nph), dtype=g2.dtype)
    my_wg = np.empty(sizes[comm.rank])

    d2 = np.empty((nk, nk, nel, nel))

    k1 = slice(0, nk)
    k2 = slice(0, nk)

    for my_iq, iq in enumerate(range(*bounds[comm.rank:comm.rank + 2])):
        q1 = int(round(q[iq, 0] * scale)) % nk
        q2 = int(round(q[iq, 1] * scale)) % nk

        kq1 = slice(q1, q1 + nk)
        kq2 = slice(q2, q2 + nk)

        for m in range(nel):
            for n in range(nel):
                d2[:, :, m, n] = d[kq1, kq2, m] * d[k1, k2, n]

        my_wg[my_iq] = d2.sum()

        for nu in range(nph):
            my_av[my_iq, nu] = (g2[iq, nu] * d2).sum()

    av = np.empty((nQ, nph), dtype=g2.dtype)
    wg = np.empty(nQ)

    comm.Allgatherv(my_av, (av, sizes * nph))
    comm.Allgatherv(my_wg, (wg, sizes))

    return av, wg

def triangle(q1, q2, q3, e, g1, g2, g3, kT=0.025, eps=1e-14,
        occupations=occupations.fermi_dirac, comm=comm):
    r"""Calculate triangle diagram.

    .. math::

        \chi_{\vec q \mu \vec q' \nu}
            &= \sum_{\vec k \alpha \beta \gamma} \frac
            {
                \epsilon_{\vec k \alpha}
                    (f_{\vec k + \vec q \beta} - f_{\vec k + \vec q' \gamma})
                + \epsilon_{\vec k + \vec q \beta}
                    (f_{\vec k + \vec q' \gamma} - f_{\vec k \alpha})
                + \epsilon_{\vec k + \vec q' \gamma}
                    (f_{\vec k \alpha} - f_{\vec k + \vec q \beta})
            }{
                (\epsilon_{\vec k + \vec q \beta}
                    - \epsilon_{\vec k + \vec q' \gamma})
                (\epsilon_{\vec k + \vec q' \gamma}
                    - \epsilon_{\vec k \alpha})
                (\epsilon_{\vec k \alpha}
                    - \epsilon_{\vec k + \vec q \beta})
            }
            \\ &\times
            g^*_{\vec q \mu \vec k \beta \alpha}
            g_{\vec q' \nu \vec k \gamma \alpha}
            g_{\vec q - \vec q' \nu \vec k + \vec q' \beta \gamma}

    .. code-block:: text

                   q u
                    o
                   / \
                  /   \
                 /     \
           k a  v       ^  k+q b
               /         \
              /           \
             /             \
            o------->-------o
        q' v     k+q' c      q-q' v

    Parameters
    ----------
    q1, q2, q3 : 2-tuples
        q points of the vertices in crystal coordinates :math:`q_1, q_2 \in [0,
        2 \pi)`.  In the above diagram, :math:`q_1 = q, q_2 = q', q3 = q - q'`.
    e : ndarray
        Electron dispersion on uniform mesh. The Fermi level must be at zero.
    g1, g2, g3 : ndarray
        Electron-phonon coupling for given q points.
    kT : float
        Smearing temperature.
    eps : float
        Smallest allowed absolute value of divisor.
    occupations : function
        Particle distribution as a function of energy divided by `kT`.

    Returns
    -------
    ndarray
        Value of triangle.
    """
    nk, nk, nbnd = e.shape

    x = e / kT

    f = occupations(x)
    d = occupations.delta(x) / kT

    e  = np.tile(e,  (2, 2, 1))
    f  = np.tile(f,  (2, 2, 1))
    d  = np.tile(d,  (2, 2, 1))
    g1 = np.tile(g1, (2, 2, 1, 1))
    g2 = np.tile(g2, (2, 2, 1, 1))
    g3 = np.tile(g3, (2, 2, 1, 1))

    scale = nk / (2 * np.pi)
    prefactor = 1.0 / nk ** 2

    chi = np.empty((nbnd, nbnd, nbnd, nk, nk), dtype=complex)

    q11 = int(round(q1[0] * scale)) % nk
    q12 = int(round(q1[1] * scale)) % nk

    q21 = int(round(q2[0] * scale)) % nk
    q22 = int(round(q2[1] * scale)) % nk

    k1 = slice(0, nk)
    k2 = slice(0, nk)

    kq1 = slice(q11, q11 + nk)
    kq2 = slice(q12, q12 + nk)

    kQ1 = slice(q21, q21 + nk)
    kQ2 = slice(q22, q22 + nk)

    for a in range(nbnd):
        ea = e[k1, k2, a]
        fa = f[k1, k2, a]
        da = d[k1, k2, a]

        for b in range(nbnd):
            eb = e[kq1, kq2, b]
            fb = f[kq1, kq2, b]
            db = d[kq1, kq2, b]

            for c in range(nbnd):
                ec = e[kQ1, kQ2, c]
                fc = f[kQ1, kQ2, c]
                dc = d[kQ1, kQ2, c]

                dea = eb - ec
                deb = ec - ea
                dec = ea - eb

                dfa = fb - fc
                dfb = fc - fa
                dfc = fa - fb

                la = abs(dea) > eps
                lb = abs(deb) > eps
                lc = abs(dec) > eps

                l = la & lb & lc; L = l
                chi[a, b, c][l] \
                    = (ea[l] * dfa[l] + eb[l] * dfb[l] + ec[l] * dfc[l]) \
                    / (dea[l] * deb[l] * dec[l])

                l = ~la & lb & lc; L |= l
                chi[a, b, c][l] = (db[l] + dfc[l] / dec[l]) / dec[l]

                l = la & ~lb & lc; L |= l
                chi[a, b, c][l] = (dc[l] + dfa[l] / dea[l]) / dea[l]

                l = la & lb & ~lc; L |= l
                chi[a, b, c][l] = (da[l] + dfb[l] / deb[l]) / deb[l]

                l = ~L
                chi[a, b, c][l] = da[l] * (0.5 - fa[l])

    chi = np.einsum('abckl,klba,klca,klbc', chi,
        g1[k1, k2].conj(), g2[k1, k2], g3[kQ1, kQ2])

    return prefactor * chi.sum()
