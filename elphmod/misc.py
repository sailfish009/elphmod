#!/usr/bin/env python3

# Copyright (C) 2021 elphmod Developers
# This program is free software under the terms of the GNU GPLv3 or later.

import numpy as np
import sys

from . import MPI
comm = MPI.comm

Ry = 13.605693009 # Rydberg energy (eV)
a0 = 0.52917721090380 # Bohr radius (AA)
kB = 8.61733e-5 # Boltzmann constant (eV/K)

class StatusBar(object):
    def __init__(self, count, width=60, title='progress'):
        if comm.rank:
            return

        self.counter = 0
        self.count = count
        self.width = width
        self.progress = 0

        sys.stdout.write((' %s ' % title).center(width, '_'))
        sys.stdout.write('\n')

    def update(self):
        if comm.rank:
            return

        self.counter += 1

        progress = self.width * self.counter // self.count

        if progress != self.progress:
            sys.stdout.write('=' * (progress - self.progress))
            sys.stdout.flush()

            self.progress = progress

        if self.counter == self.count:
            sys.stdout.write('\n')

def group(points, eps=1e-7):
    """Group points into neighborhoods.

    Parameters
    ----------
    points : ndarray
        Points to be grouped.
    eps : float
        Maximal distance between points in the same group.

    Returns
    -------
    list of lists
        Groups of indices.
    """
    groups = np.arange(len(points))

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if np.all(np.absolute(points[j] - points[i]) < eps):
                groups[np.where(groups == groups[j])] = groups[i]

    return [np.where(groups == group)[0] for group in set(groups)]
