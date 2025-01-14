# logs size is 24 records long, splitted in 3 files of 8 events each

import pytest
import os
from ambianic.webapp.server import samples
import logging

log = logging.getLogger(__name__)


sample_id = "test_id"
sample = {
        'file': '20190913-063945-json.txt',
        'id': sample_id,
        "datetime": "2019-09-13T16:32:34.704797",
        "image": "20190913-163234-image.jpg",
        "inference_result": [{
            "category": "person",
            "confidence": 0.98046875,
            "box": {
                "xmin": 0.5251423732654468,
                "ymin": 0.0021262094378471375,
                "xmax": 0.9498447340887946,
                "ymax": 0.23079824447631836
            }
        }]
    }


def test_get_timeline_overflow():
    data_dir = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "./timeline")
    res = samples.get_timeline(
        before_datetime=None,
        page=7,
        data_dir=data_dir
    )
    assert len(res) == 0


def test_get_timelines_no_dir():
    data_dir = "nowhere"
    res = samples.get_timeline(
        before_datetime=None,
        page=1,
        data_dir=data_dir
    )
    assert len(res) == 0


def test_empty_list():
    data_dir = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "./pipeline")
    res = samples.get_timeline(
        before_datetime=None,
        page=1,
        data_dir=data_dir
    )
    assert len(res) == 0


def test_get_timelines_before_datetime():
    data_dir = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "./timeline")
    res = samples.get_timeline(
        before_datetime="2020-05-10T19:05:45.577145",
        page=1,
        data_dir=data_dir
    )
    assert len(res) == 5


def test_get_timelines():
    data_dir = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "./timeline")
    for page in range(1, 6):
        res = samples.get_timeline(
            before_datetime=None,
            page=page,
            data_dir=data_dir
        )
        assert len(res) > 0
        assert res[0]["id"] == "page%d" % page


def test_add_sample():
    assert not samples.add_sample(sample)


def test_update_sample():
    samples.add_sample(sample)
    assert samples.update_sample(sample)


def test_update_sample_not_found():
    samples.add_sample(sample)
    assert not samples.update_sample({"id": "not_found"})


def test_delete_sample():
    samples.add_sample(sample)
    assert samples.delete_sample(sample["id"])


def test_delete_sample_not_avail():
    samples.add_sample(sample)
    assert not samples.delete_sample("not_found")
