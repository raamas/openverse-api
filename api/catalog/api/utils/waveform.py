import json
import logging
import math
import mimetypes
import os
import pathlib
import shutil
import subprocess

import requests


log = logging.getLogger(__name__)

TMP_DIR = pathlib.Path("/tmp").resolve()
UA_STRING = "OpenverseWaveform/0.0 (https://wordpress.org/openverse)"


def ext_from_url(url):
    """
    Get the file extension from the given URL. Looks at the last part of the URL
    path, and returns the string after the last dot.

    :param url: the URL to the file whose extension is being determined
    :returns: the file extension or ``None``
    """
    file_name = url.split("/")[-1]
    if "." in file_name:
        ext = file_name.split(".")[-1]
        return f".{ext}"
    else:
        return None


def download_audio(url, identifier):
    """
    Download the audio from the given URL to a location on the disk.

    :param url: the URL to the file being downloaded
    :param identifier: the identifier of the media object to name the file
    :returns: the name of the file on the disk
    """
    log.info(f"Downloading file at {url}")

    headers = {"User-Agent": UA_STRING}
    with requests.get(url, stream=True, headers=headers) as res:
        log.debug(f"Response code: {res.status_code}")
        mimetype = res.headers["content-type"]
        log.debug(f"MIME type: {mimetype}")
        ext = ext_from_url(url) or mimetypes.guess_extension(mimetype)
        if ext is None:
            raise ValueError("Could not identify media extension")
        file_name = f"audio-{identifier}{ext}"
        log.debug(f"File name: {file_name}")
        with open(TMP_DIR.joinpath(file_name), "wb") as file:
            shutil.copyfileobj(res.raw, file)
    return file_name


def generate_waveform(file_name, duration):
    """
    Generate the waveform for the file by invoking the ``audiowaveform`` binary.
    The Python module ``subprocess`` is used to execute the binary and get the
    results that it emits to STDOUT.

    :param file_name: the name of the downloaded audio file
    :param duration: the duration of the audio to determine pixels per second
    """
    log.info("Invoking audiowaveform")

    pps = math.ceil(1e6 / duration)  # approx 1000 points in total
    args = [
        "audiowaveform",
        "--input-filename",
        file_name,
        "--output-format",
        "json",
        "--pixels-per-second",
        str(pps),
    ]
    log.debug(f'Command: {" ".join(args)}')
    proc = subprocess.run(args, cwd=TMP_DIR, check=True, capture_output=True)
    log.debug(f"Subprocess exit code: {proc.returncode}")
    return proc.stdout


def process_waveform_output(json_out):
    """
    Parse the waveform output generated by the ``audiowaveform`` binary. The
    output consists of alternating positive and negative values, that are almost
    equal in amplitude. We discard the negative values. We also scale down the
    amplitudes by the largest value so that they lie in the range [0, 1].

    :param json_out: the JSON output generated by ``audiowaveform``
    :returns: the list of peaks
    """
    log.info("Transforming points")

    output = json.loads(json_out)
    data = output["data"]
    log.debug(f"Original umber of points: {len(data)}")

    transformed_data = []
    max_val = 0
    for idx, val in enumerate(data):
        if idx % 2 == 0:
            continue
        transformed_data.append(val)
        if val > max_val:
            max_val = val
    transformed_data = [round(val / max_val, 5) for val in transformed_data]
    log.debug(f"Transformed number of points: {len(transformed_data)}")
    return transformed_data


def cleanup(file_name):
    """
    Delete the audio file after it has been processed.

    :param file_name: the name of the file to delete
    """
    log.info(f"Deleting {file_name}")

    file_path = TMP_DIR.joinpath(file_name)
    log.debug(f"File path: {file_path}")
    if file_path.exists():
        log.info(f"Deleting file {file_path}")
        os.remove(file_path)
    else:
        log.info("File not found, nothing deleted")