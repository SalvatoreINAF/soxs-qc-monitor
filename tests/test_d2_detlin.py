"""Sequence identity, independent fits and atomic day/arm persistence."""
from pathlib import Path
import shutil

from astropy.io import fits
import numpy as np
import pytest

from conftest import DAY, database_snapshot, rows
from qc_monitor.detector_linearity import load_detector_linearity_data, _fit_detector_linearity_rows
from qc_monitor.main import consolidate_detector_linearity
from qc_monitor.plotting import select_detector_linearity_sequences, plot_detector_linearity_from_config
from qc_monitor.storage import SQLiteStore


def second_sequence(lab, *, multiplier=2):
    directory = lab.raw / 'second'
    directory.mkdir()
    for original in lab.raw.glob('*.fits'):
        destination = directory / original.name
        shutil.copyfile(original, destination)
        with fits.open(destination, mode='update') as hdus:
            hdus[0].header['ESO TPL START'] = DAY + 'T10:00:00'
            hdus[0].header['DATE-OBS'] = hdus[0].header['DATE-OBS'].replace('T08:', 'T10:')
            if 'BIAS' not in original.name and 'DARK' not in original.name:
                hdus[0].data = 10 + multiplier * (hdus[0].data - 10)
    return directory


@pytest.mark.parametrize('arm', ['VIS', 'NIR'])
def test_two_sequences_have_separate_fits_and_one_atomic_registry(lab, arm):
    lab.detlin(arm=arm)
    second_sequence(lab)
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT count(*) FROM detlin_sequences') == [(2,)]
    assert rows(lab.db, 'SELECT count(*) FROM processed_detector_linearity_obs_days') == [(1,)]
    results = store.load_detector_linearity_results()
    assert set(np.round(results.slope, 8)) == {100., 200.}
    assert results.sequence_id.nunique() == 2
    assert results.groupby('sequence_id').slope.nunique().eq(1).all()
    assert results.fit_state.eq('available').all()
    before = database_snapshot(lab.db)
    assert consolidate_detector_linearity(lab.cfg, store) == 0
    assert database_snapshot(lab.db) == before
    latest = select_detector_linearity_sequences(results, 'latest')
    assert latest.sequence_id.nunique() == 1
    assert latest.slope.to_numpy() == pytest.approx([200.] * len(latest), rel=1e-10, abs=1e-8)


@pytest.mark.parametrize('already_closed', [False, True])
def test_one_incomplete_sequence_prevents_entire_day_replacement(lab, already_closed):
    lab.detlin()
    store = SQLiteStore(lab.db)
    if already_closed:
        consolidate_detector_linearity(lab.cfg, store)
    second = second_sequence(lab)
    damaged = second / 'SOXS_GEN_FLAT_VIS_DETLIN_SHG_UIT2_278_0002.fits'
    bytes_before = damaged.read_bytes()
    damaged.write_bytes(b'broken FITS')
    before = database_snapshot(lab.db)
    consolidate_detector_linearity(lab.cfg, store, force=already_closed)
    assert database_snapshot(lab.db) == before
    damaged.write_bytes(bytes_before)
    consolidate_detector_linearity(lab.cfg, store, force=already_closed)
    assert rows(lab.db, 'SELECT count(*) FROM detlin_sequences') == [(2,)]
    assert rows(lab.db, 'SELECT count(DISTINCT filepath) FROM detector_linearity_measurements') == [(56,)]


@pytest.mark.parametrize('damage', ['binning', 'image-size', 'zero-bin', 'fractional-bin'])
def test_geometry_incoherence_or_invalid_binning_keeps_day_open(lab, damage):
    lab.detlin()
    file = lab.raw / 'SOXS_GEN_FLAT_VIS_DETLIN_SHG_UIT2_278_0002.fits'
    with fits.open(file, mode='update') as hdus:
        if damage == 'image-size':
            hdus[0].data = np.full((3, 2), 210.)
        else:
            hdus[0].header['HIERARCH ESO DET BINX'] = {'binning': 2, 'zero-bin': 0, 'fractional-bin': 1.5}[damage]
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []
    assert rows(lab.db, 'SELECT * FROM detlin_sequences') == []


def test_constant_binning_is_recorded_without_signal_rescaling(lab):
    lab.detlin()
    for file in lab.raw.glob('*.fits'):
        with fits.open(file, mode='update') as hdus:
            hdus[0].header['HIERARCH ESO DET BINX'] = 2
            hdus[0].header['HIERARCH ESO DET BINY'] = 2
    measurements, results = load_detector_linearity_data(lab.cfg)
    assert measurements.binning_assumed.eq(0).all()
    assert measurements.bin_x.eq(2).all() and measurements.bin_y.eq(2).all()
    assert results.slope.to_numpy() == pytest.approx([100.] * len(results), rel=1e-10, abs=1e-8)
    assert set(measurements.image_width) == set(measurements.image_height) == {2}


def test_missing_binning_is_explicit_and_unavailable_fit_has_no_fake_zero(lab, caplog):
    lab.detlin(times=(1,))
    measurements, results = load_detector_linearity_data(lab.cfg)
    assert measurements.binning_assumed.eq(1).all()
    assert measurements.bin_x.eq(1).all() and measurements.bin_y.eq(1).all()
    assert 'assumed to be 1' in caplog.text
    assert results.fit_state.eq('unavailable').all()
    assert results.fit_reason.str.len().gt(0).all()
    assert results[['slope', 'intercept', 'fit_signal', 'residual', 'residual_percent']].isna().all().all()
    assert results.fit_used.eq(0).all()


def test_multisequence_registry_failure_rolls_back_sequence_metadata(lab):
    from test_unit_recovery import execute
    lab.detlin()
    second_sequence(lab)
    store = SQLiteStore(lab.db)
    execute(lab.db, "CREATE TRIGGER stop BEFORE INSERT ON processed_detector_linearity_obs_days BEGIN SELECT RAISE(ABORT, 'stop'); END")
    before = database_snapshot(lab.db)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        consolidate_detector_linearity(lab.cfg, store)
    assert database_snapshot(lab.db) == before


def test_plot_all_keeps_sequence_curves_separate(lab, monkeypatch):
    import matplotlib.pyplot as plt
    import qc_monitor.plotting as plotting
    lab.detlin()
    second_sequence(lab)
    _, results = load_detector_linearity_data(lab.cfg)
    captured = []
    original_save = plotting._save_figure
    def save(path, fig=None):
        captured.extend((line.get_xdata().copy(), line.get_ydata().copy(), line.get_label())
                        for line in fig.axes[0].lines if line.get_label().endswith('Measured'))
        original_save(path, fig)
    monkeypatch.setattr(plotting, '_save_figure', save)
    plot_detector_linearity_from_config(results, {'name': 'vis_sequences', 'arm': 'VIS', 'filename': 'all.png',
        'selection': 'all', 'mode_order': ['SHG'], 'figsize': [9, 5]}, lab.output)
    assert len(captured) == 2
    assert all(len(x) == 2 for x, _, _ in captured)
    assert {label.split(' — ')[0] for _, _, label in captured} == {
        DAY + ' 08:00:00+00:00 SOXS_gen_tec_VISDetLin', DAY + ' 10:00:00+00:00 SOXS_gen_tec_VISDetLin'}
    assert (lab.output / 'all.png').stat().st_size > 1000
    assert not plt.get_fignums()


def test_latest_tie_is_deterministic(lab):
    lab.detlin()
    _, results = load_detector_linearity_data(lab.cfg)
    copy = results.copy()
    copy['sequence_id'] = 'zzzz'
    import pandas as pd
    combined = pd.concat([copy, results])
    assert set(select_detector_linearity_sequences(combined, 'latest').sequence_id) == {'zzzz'}
    assert set(select_detector_linearity_sequences(combined.iloc[::-1], 'latest').sequence_id) == {'zzzz'}


@pytest.mark.parametrize('invalid', ['bad', -1, float('nan')])
def test_invalid_declared_time_is_not_coerced_to_zero(lab, invalid):
    lab.detlin()
    # FITS cannot encode NaN as a header float; use its explicit textual form.
    with fits.open(lab.raw / 'SOXS_GEN_FLAT_VIS_DETLIN_SHG_UIT2_278_0002.fits', mode='update') as hdus:
        hdus[0].header['ESO DET UIT1'] = 'nan' if isinstance(invalid, float) else invalid
    store = SQLiteStore(lab.db)
    consolidate_detector_linearity(lab.cfg, store)
    assert rows(lab.db, 'SELECT * FROM processed_detector_linearity_obs_days') == []


def test_zero_pair_variance_is_missing_gain_not_physical_zero(lab):
    lab.detlin()
    for mode in ('SHG', 'FLG', 'SLG', 'FHG'):
        for time in (1, 2):
            first = lab.raw / f'SOXS_GEN_FLAT_VIS_DETLIN_{mode}_UIT{time}_278_0001.fits'
            second = lab.raw / f'SOXS_GEN_FLAT_VIS_DETLIN_{mode}_UIT{time}_278_0002.fits'
            with fits.open(second, mode='update') as hdus:
                hdus[0].data = fits.getdata(first)
    _, results = load_detector_linearity_data(lab.cfg)
    assert results.cf.isna().all()
    assert results.rms_bias_e.isna().all()
    assert results.slope.to_numpy() == pytest.approx([100.] * len(results), rel=1e-10, abs=1e-8)
