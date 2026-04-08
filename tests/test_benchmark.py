"""Smoke tests for router performance — ensures no regressions."""

import time

from FasterAPI.router import RadixRouter


class TestRouterPerformance:
    def test_registration_under_100ms(self):
        router = RadixRouter()
        start = time.perf_counter()
        for i in range(1_000):
            router.add_route("GET", f"/api/v1/resource{i}", lambda: None)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"1k registrations took {elapsed:.3f}s"

    def test_static_resolution_throughput(self):
        router = RadixRouter()
        for i in range(100):
            router.add_route("GET", f"/api/v1/resource{i}", lambda: None)

        start = time.perf_counter()
        for _ in range(10_000):
            router.resolve("GET", "/api/v1/resource50")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"10k static resolves took {elapsed:.3f}s"

    def test_param_resolution_throughput(self):
        router = RadixRouter()
        router.add_route("GET", "/users/{user_id}/posts/{post_id}", lambda: None)

        start = time.perf_counter()
        for _ in range(10_000):
            result = router.resolve("GET", "/users/42/posts/99")
            assert result is not None
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"10k param resolves took {elapsed:.3f}s"

    def test_many_routes_no_degradation(self):
        router = RadixRouter()
        for i in range(500):
            router.add_route("GET", f"/section{i}/items/{{id}}", lambda: None)

        start = time.perf_counter()
        for _ in range(5_000):
            router.resolve("GET", "/section250/items/42")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"5k resolves over 500 routes took {elapsed:.3f}s"
