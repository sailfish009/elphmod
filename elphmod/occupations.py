#/usr/bin/env python

import math
import numpy as np
import sys

from . import misc
kB = misc.kB

xmax = 709.0 # approx. log([max. double] / 2 - 1)

def fermi_dirac(x):
    """Calculate Fermi function."""

    # return 1 - 0.5 * np.tanh(0.5 * x)

    x = np.minimum(x, xmax)

    return 1 / (np.exp(x) + 1)

def fermi_dirac_delta(x):
    """Calculate negative derivative of Fermi function."""

    x = np.minimum(np.absolute(x), xmax)

    return 1 / (2 * np.cosh(x) + 2)

fermi_dirac.delta = fermi_dirac_delta

def gauss(x):
    """Calculate Gaussian step function."""

    return 0.5 * (1 - math.erf(x))

if 'sphinx' not in sys.modules:
    gauss = np.vectorize(gauss)

def gauss_delta(x):
    """Calculate negative derivative of Gaussian step function."""

    return np.exp(-x * x) / np.sqrt(np.pi)

gauss.delta = gauss_delta

def methfessel_paxton_general(x, N=0):
    r"""Calculate Methfessel-Paxton step function and its negative derivative.

    From Phys. Rev. B 40, 3616 (1989):

    .. math::

        S_0(x) &= \frac {1 - erf(x)} 2 \\
        S_N(x) &= S_0(x) + \sum_{n = 1}^N A_n H_{2 n - 1}(x) \exp(-x^2) \\
        D_N(x) &= -S'(N, x) = \sum{n = 0}^N A_n H_{2 n}(x) \exp(-x^2) \\
        A_n &= \frac{(-1)^n}{\sqrt \pi n! 4^n}

    Hermite polynomials:

    .. math::

        H_0(x) &= 1 \\
        H_1(x) &= 2 x \\
        H_{n + 1}(x) &= 2 x H_n(x) - 2 n H_{n - 1}(x) \\

    For ``N = 0``, the Gaussian step function is returned.

    This routine has been adapted from Quantum ESPRESSO:

    * Step function: Modules/wgauss.f90
    * Delta function: Modules/w0gauss.f90
    """
    S = gauss(x)
    D = gauss_delta(x)

    # In the following, our Hermite polynomials (`H` and `h`) are defined such
    # that they contain the factor exp(-x^2) / sqrt(pi) = D(0, x). On the other
    # hand, our coefficient A(n) (`a`) does not contain the factor 1 / sqrt(pi).

    H = 0 # H(-1, x)
    h = D # H( 0, x)

    a = 1.0
    m = 0

    for n in range(1, N + 1):
        H = 2 * x * h - 2 * m * H # H(1, x), H(3, x), ...
        m += 1

        h = 2 * x * H - 2 * m * h # H(2, x), H(4, x), ...
        m += 1

        a /= -4 * n

        S += a * H
        D += a * h

    return S, D

if 'sphinx' not in sys.modules:
    methfessel_paxton_general = np.vectorize(methfessel_paxton_general)

def methfessel_paxton(x):
    """Calculate first-order Methfessel-Paxton step function."""

    return methfessel_paxton_general(x, N=1)[0]

def methfessel_paxton_delta(x):
    """Calculate negative derivative of first-order MP step function."""

    return methfessel_paxton_general(x, N=1)[1]

methfessel_paxton.delta = methfessel_paxton_delta

def lorentz(x):
    """Calculate Lorentz step function.

    Used to simulate the influence of a wide box-shaped hybridization function
    at low temperatures. Formula derived by Tim O. Wehling and Erik G.C.P. van
    Loon. Here, we have :math:`x = \epsilon / h` with the height :math:`h` of
    the hybridization, instead of :math:`x = \epsilon / k T` with the
    temperature :math:`T`.
    """
    return 0.5 - np.arctan(x / np.pi) / np.pi

def lorentz_delta(x):
    """Calculate negative derivative of Lorentz step function."""

    return 1.0 / (x * x + np.pi * np.pi)

lorentz.delta = lorentz_delta

def fermi_dirac_matsubara(x, nmats=1000):
    """Calculate Fermi function as Matsubara sum."""

    inu = 1j * (2 * np.arange(nmats) + 1) * np.pi

    return 0.5 + 2 * np.sum(1.0 / (inu - x)).real

if 'sphinx' not in sys.modules:
    fermi_dirac_matsubara = np.vectorize(fermi_dirac_matsubara)

def fermi_dirac_matsubara_delta(x, nmats=1000):
    """Calculate negative derivative of Fermi function as Matsubara sum."""

    inu = 1j * (2 * np.arange(nmats) + 1) * np.pi

    return -2 * np.sum(1.0 / (inu - x) ** 2).real

if 'sphinx' not in sys.modules:
    fermi_dirac_matsubara_delta = np.vectorize(fermi_dirac_matsubara_delta)

fermi_dirac_matsubara.delta = fermi_dirac_matsubara_delta

if __name__ == '__main__':
    # check if int[a, b] df = f(b) - f(a):

    a, b = 5 * (1 - 2 * np.random.random(2))

    x, dx = np.linspace(a, b, 10000, retstep=True)
    y, dy = methfessel_paxton_general(x, N=1)

    dy[ 0] /= 2
    dy[-1] /= 2

    print('int[a, b] df = %.7f' % (-dy.sum() * dx))
    print(' f(b) - f(a) = %.7f' % (y[-1] - y[0]))
