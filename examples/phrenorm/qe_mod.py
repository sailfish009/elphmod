#!/usr/bin/env python3

# Copyright (C) 2021 elphmod Developers
# This program is free software under the terms of the GNU GPLv3 or later.

import sys

if len(sys.argv) > 1:
    QE = sys.argv[1]
else:
    print('''Usage: python3 qe_mod.py /path/to/q-e/

ATTENTION: This script will modify QE sources files without backup!
Use QE's Git repository and verify or undo changes with "git diff"!
The changes are compatible with version "qe-6.7MaX-Release" only!''')

    raise SystemExit

def modify(filename, *args):
    path = '/'.join((QE, filename))

    with open(path) as source:
        lines = source.readlines()

    def join(i, j=len(lines)):
        return ''.join(lines[i - 1:j])

    with open(path, 'w') as new:
        for arg in args:
            if type(arg) is tuple:
                new.write(join(*arg))
            else:
                new.write(arg.lstrip('\n'))

modify('LR_Modules/lrcom.f90', (1, 66), r'''
  LOGICAL  :: cdfpt          ! if .TRUE. applies cDFPT
  INTEGER, ALLOCATABLE :: cdfpt_subspace(:, :, :, :)
''', (67,))

modify('LR_Modules/orthogonalize.f90', (1, 31), r'''
  USE klist,            ONLY : lgauss, degauss, ngauss, ltetra, wk, xk
  USE start_k,          ONLY : nk1, nk2, nk3
  USE cell_base,        ONLY : at
''', (33, 42), r'''
  USE control_lr,       ONLY : alpha_pv, nbnd_occ, cdfpt, cdfpt_subspace
''', (44, 55), r'''
  INTEGER :: ibnd, jbnd, nbnd_eff, n_start, n_end, kk1, kk2, kk3, kq1, kq2, kq3
''', (57, 59), r'''
  !
  kk1 = modulo(nint(nk1 * dot_product(at(:, 1), xk(:, ikk))), nk1) + 1
  kk2 = modulo(nint(nk2 * dot_product(at(:, 2), xk(:, ikk))), nk2) + 1
  kk3 = modulo(nint(nk3 * dot_product(at(:, 3), xk(:, ikk))), nk3) + 1
  !
  kq1 = modulo(nint(nk1 * dot_product(at(:, 1), xk(:, ikq))), nk1) + 1
  kq2 = modulo(nint(nk2 * dot_product(at(:, 2), xk(:, ikq))), nk2) + 1
  kq3 = modulo(nint(nk3 * dot_product(at(:, 3), xk(:, ikq))), nk3) + 1
''', (60, 92), r'''
              IF (cdfpt) THEN
                 IF (any(cdfpt_subspace(:, kk1, kk2, kk3) == ibnd) .AND. &
                     any(cdfpt_subspace(:, kq1, kq2, kq3) == jbnd)) THEN
                    ps(jbnd, ibnd) = wg1 * ps(jbnd, ibnd)
                    CYCLE
                 ENDIF
              ENDIF
              !
''', (93,))

modify('PHonon/PH/phq_readin.f90', (1, 68), r'''
  USE control_lr,    ONLY : lgamma, lrpa, cdfpt, cdfpt_subspace
''', (70, 112), r'''
  CHARACTER(LEN=256) :: subspace
  !
''', (113, 128), r'''
                       skip_upperfan, cdfpt, subspace
''', (130, 341), r'''
  cdfpt = .false.
  subspace = 'subspace.dat'
  !
''', (342, 388), r'''
  !
  CALL mp_bcast(cdfpt, meta_ionode_id, world_comm)
  IF (cdfpt) CALL setup_subspace(cdfpt_subspace, subspace)
''', (389, 961), r'''
CONTAINS
  !
  SUBROUTINE setup_subspace(subspace, filename)
     INTEGER, ALLOCATABLE, INTENT(OUT) :: subspace(:, :, :, :)
     CHARACTER(LEN=256), INTENT(IN) :: filename
     !
     INTEGER, EXTERNAL :: find_free_unit
     INTEGER :: id, nk(3), bands, band, offset
     !
     id = find_free_unit()
     !
     IF (meta_ionode) THEN
        OPEN (id, file=filename, action='read', status='old')
        READ (id, *) nk, bands, offset
     ENDIF
     !
     CALL mp_bcast(nk, meta_ionode_id, world_comm)
     CALL mp_bcast(bands, meta_ionode_id, world_comm)
     !
     ALLOCATE(subspace(bands, nk(1), nk(2), nk(3)))
     !
     IF (meta_ionode) THEN
        DO band = 1, bands
           READ (id, *) subspace(band, :, :, :)
        ENDDO
        CLOSE (id)
        subspace(:, :, :, :) = subspace + offset
     ENDIF
     !
     CALL bcast_integer(subspace, size(subspace), meta_ionode_id, world_comm)
  END SUBROUTINE
''', (962,))

modify('EPW/src/ephwann_shuffle.f90', (1, 376), r'''
  !
  IF (ionode) THEN
    OPEN (13, file='wigner.dat', action='write', status='replace', access='stream')
    WRITE (13) dims, dims2
    WRITE (13) nrr_k, irvec_k, ndegen_k
    WRITE (13) nrr_g, irvec_g, ndegen_g
    CLOSE (13)
  ENDIF
  !
''', (377,))
