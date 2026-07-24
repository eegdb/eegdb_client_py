def read_brainvision(*args, **kwargs):
    from .brainvision_reader import read_brainvision as _read_brainvision

    return _read_brainvision(*args, **kwargs)


def read_edf(*args, **kwargs):
    from .edf_reader import read_edf as _read_edf

    return _read_edf(*args, **kwargs)


def read_fif(*args, **kwargs):
    from .fif_reader import read_fif as _read_fif

    return _read_fif(*args, **kwargs)

__all__ = ["read_brainvision", "read_edf", "read_fif"]
