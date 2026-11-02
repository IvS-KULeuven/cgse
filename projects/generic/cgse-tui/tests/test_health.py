"""Tests for judging the CPU and memory use of a process."""

from cgse_tui.data import health
from cgse_tui.data.model import Level
from cgse_tui.data.model import ServiceInfo


def samples(values, pid=1, interval=1.0, rss=None, cpu=0.0):
    """(time, pid, cpu %, rss) samples, one per interval, from time 0."""
    if rss is None:
        return [(index * interval, pid, value, 100 * 2**20) for index, value in enumerate(values)]
    return [(index * interval, pid, cpu, value) for index, value in enumerate(rss)]


def test_cpu_average_over_the_last_minute():
    assert health.cpu_level(samples([2.0] * 61), now=60.0) == (Level.OK, "")
    level, reason = health.cpu_level(samples([60.0] * 61), now=60.0)
    assert level is Level.WARNING and reason == "average CPU 60 % over the last 60 s"
    assert health.cpu_level(samples([95.0] * 61), now=60.0)[0] is Level.CRITICAL
    # a short peak doesn't count
    assert health.cpu_level(samples([2.0] * 55 + [100.0] * 6), now=60.0)[0] is Level.OK
    # too few samples: not judged yet
    assert health.cpu_level(samples([95.0] * 10), now=10.0)[0] is Level.OK


def test_memory_growth_over_ten_minutes():
    steady = [100 * 2**20] * 601
    assert health.memory_level(samples(None, rss=steady), now=600.0) == (Level.OK, "")

    growing = [int((100 + 15 * index / 600) * 2**20) for index in range(601)]  # 100 → 115 MiB
    level, reason = health.memory_level(samples(None, rss=growing), now=600.0)
    assert level is Level.WARNING
    assert reason.startswith("memory grew 11% in 10 min") and reason.endswith("a leak?")

    leaking = [int((100 + 40 * index / 600) * 2**20) for index in range(601)]
    assert health.memory_level(samples(None, rss=leaking), now=600.0)[0] is Level.CRITICAL

    # the growth while the process starts is not judged: less than half of the window
    assert health.memory_level(samples(None, rss=leaking[:200]), now=200.0)[0] is Level.OK


def test_samples_of_a_new_process_start_over():
    service = ServiceInfo(name="AWG1", service_type="AWG1", pid=1, cpu_percent=1.0, rss=10)
    service.add_sample(0.0)
    service.add_sample(1.0)
    service.pid = 2
    service.add_sample(2.0)
    assert [sample[:2] for sample in service.samples] == [(2.0, 2)]


def test_old_samples_are_dropped():
    service = ServiceInfo(name="AWG1", service_type="AWG1", pid=1, cpu_percent=1.0, rss=10)
    for t in range(0, 1000, 10):
        service.add_sample(float(t))
    assert service.samples[0][0] >= 990 - 900


def test_assess_sets_the_levels():
    service = ServiceInfo(name="AWG1", service_type="AWG1")
    service.samples.extend(samples([95.0] * 61))
    health.assess(service, now=60.0)
    assert service.cpu_level is Level.CRITICAL and service.memory_level is Level.OK
