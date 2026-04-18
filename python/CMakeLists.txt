# Copyright 2011 Free Software Foundation, Inc.
#
# This file is part of GNU Radio
#
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.

########################################################################
# Include python install macros
########################################################################
include(GrPython)
if(NOT PYTHONINTERP_FOUND)
    return()
endif()

########################################################################
# Install python sources
########################################################################
GR_PYTHON_INSTALL(
    FILES
    __init__.py
    DESTINATION ${GR_PYTHON_DIR}/dsd
)

########################################################################
# Install the wideband sub-package
########################################################################
set(WIDEBAND_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/wideband)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/__init__.py
    ${WIDEBAND_ROOT}/__main__.py
    ${WIDEBAND_ROOT}/cli.py
    ${WIDEBAND_ROOT}/config.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/ingest/__init__.py
    ${WIDEBAND_ROOT}/ingest/readers.py
    ${WIDEBAND_ROOT}/ingest/stream.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/ingest
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/detect/__init__.py
    ${WIDEBAND_ROOT}/detect/events.py
    ${WIDEBAND_ROOT}/detect/psd.py
    ${WIDEBAND_ROOT}/detect/cfar.py
    ${WIDEBAND_ROOT}/detect/tracker.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/detect
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/classify/__init__.py
    ${WIDEBAND_ROOT}/classify/features.py
    ${WIDEBAND_ROOT}/classify/rules.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/classify
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/extract/__init__.py
    ${WIDEBAND_ROOT}/extract/channelizer.py
    ${WIDEBAND_ROOT}/extract/fm_demod.py
    ${WIDEBAND_ROOT}/extract/resample.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/extract
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/decode/__init__.py
    ${WIDEBAND_ROOT}/decode/dsd_runner.py
    ${WIDEBAND_ROOT}/decode/dsdplus_runner.py
    ${WIDEBAND_ROOT}/decode/tetra_runner.py
    ${WIDEBAND_ROOT}/decode/dpmr_runner.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/decode
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/crypto/__init__.py
    ${WIDEBAND_ROOT}/crypto/p25_enc.py
    ${WIDEBAND_ROOT}/crypto/dmr_pi.py
    ${WIDEBAND_ROOT}/crypto/tetra_enc.py
    ${WIDEBAND_ROOT}/crypto/report.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/crypto
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/crypto/attacks/__init__.py
    ${WIDEBAND_ROOT}/crypto/attacks/iv_reuse.py
    ${WIDEBAND_ROOT}/crypto/attacks/p25_adp.py
    ${WIDEBAND_ROOT}/crypto/attacks/p25_des.py
    ${WIDEBAND_ROOT}/crypto/attacks/dmr_bp.py
    ${WIDEBAND_ROOT}/crypto/attacks/tetra_tea1.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/crypto/attacks
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/orchestrate/__init__.py
    ${WIDEBAND_ROOT}/orchestrate/pipeline.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/orchestrate
)

GR_PYTHON_INSTALL(
    FILES
    ${WIDEBAND_ROOT}/io/__init__.py
    ${WIDEBAND_ROOT}/io/writers.py
    DESTINATION ${GR_PYTHON_DIR}/dsd/wideband/io
)
