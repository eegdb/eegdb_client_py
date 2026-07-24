def read_brainvision(*args, **kwargs):
    from .brainvision_reader import read_brainvision as _read_brainvision

    return _read_brainvision(*args, **kwargs)


def find_bids_eeg_records(*args, **kwargs):
    from .bids_reader import find_bids_eeg_records as _find_bids_eeg_records

    return _find_bids_eeg_records(*args, **kwargs)


def read_bids_eeg_record(*args, **kwargs):
    from .bids_reader import read_bids_eeg_record as _read_bids_eeg_record

    return _read_bids_eeg_record(*args, **kwargs)


def read_edf(*args, **kwargs):
    from .edf_reader import read_edf as _read_edf

    return _read_edf(*args, **kwargs)


def read_eeglab(*args, **kwargs):
    from .eeglab_reader import read_eeglab as _read_eeglab

    return _read_eeglab(*args, **kwargs)


def read_fif(*args, **kwargs):
    from .fif_reader import read_fif as _read_fif

    return _read_fif(*args, **kwargs)

__all__ = ["find_bids_eeg_records", "read_bids_eeg_record", "read_brainvision", "read_edf", "read_eeglab", "read_fif"]
