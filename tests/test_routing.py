from FasterAPI.router import RadixRouter, FasterRouter


# --- Helpers ---

def _handler():
    pass


def _other():
    pass


# --- RadixRouter: static routes ---

class TestStaticRoutes:
    def test_root(self):
        r = RadixRouter()
        r.add_route("GET", "/", _handler)
        result = r.resolve("GET", "/")
        assert result is not None
        handler, params, meta = result
        assert handler is _handler
        assert params == {}

    def test_single_segment(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        result = r.resolve("GET", "/users")
        assert result is not None
        assert result[0] is _handler
        assert result[1] == {}

    def test_multi_segment(self):
        r = RadixRouter()
        r.add_route("GET", "/api/v1/health", _handler)
        result = r.resolve("GET", "/api/v1/health")
        assert result is not None
        assert result[0] is _handler

    def test_no_match(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        assert r.resolve("GET", "/posts") is None

    def test_multiple_static_routes(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        r.add_route("GET", "/posts", _other)
        assert r.resolve("GET", "/users")[0] is _handler
        assert r.resolve("GET", "/posts")[0] is _other


# --- RadixRouter: param routes ---

class TestParamRoutes:
    def test_single_param(self):
        r = RadixRouter()
        r.add_route("GET", "/users/{id}", _handler)
        result = r.resolve("GET", "/users/42")
        assert result is not None
        handler, params, _ = result
        assert handler is _handler
        assert params == {"id": "42"}

    def test_nested_params(self):
        r = RadixRouter()
        r.add_route("GET", "/users/{user_id}/posts/{post_id}", _handler)
        result = r.resolve("GET", "/users/7/posts/99")
        assert result is not None
        handler, params, _ = result
        assert handler is _handler
        assert params == {"user_id": "7", "post_id": "99"}

    def test_param_with_static_prefix(self):
        r = RadixRouter()
        r.add_route("GET", "/api/users/{id}/profile", _handler)
        result = r.resolve("GET", "/api/users/5/profile")
        assert result is not None
        assert result[1] == {"id": "5"}

    def test_param_no_match_missing_segment(self):
        r = RadixRouter()
        r.add_route("GET", "/users/{id}/posts", _handler)
        assert r.resolve("GET", "/users/7") is None

    def test_static_preferred_over_param(self):
        r = RadixRouter()
        r.add_route("GET", "/users/me", _handler)
        r.add_route("GET", "/users/{id}", _other)
        assert r.resolve("GET", "/users/me")[0] is _handler
        assert r.resolve("GET", "/users/42")[0] is _other


# --- RadixRouter: method handling ---

class TestMethodHandling:
    def test_method_mismatch(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        assert r.resolve("POST", "/users") is None

    def test_multiple_methods_same_path(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        r.add_route("POST", "/users", _other)
        assert r.resolve("GET", "/users")[0] is _handler
        assert r.resolve("POST", "/users")[0] is _other

    def test_method_case_insensitive(self):
        r = RadixRouter()
        r.add_route("get", "/users", _handler)
        assert r.resolve("GET", "/users") is not None


# --- RadixRouter: trailing slash tolerance ---

class TestTrailingSlash:
    def test_registered_without_resolved_with(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        result = r.resolve("GET", "/users/")
        assert result is not None
        assert result[0] is _handler

    def test_registered_with_resolved_without(self):
        r = RadixRouter()
        r.add_route("GET", "/users/", _handler)
        result = r.resolve("GET", "/users")
        assert result is not None
        assert result[0] is _handler

    def test_root_with_trailing_slash(self):
        r = RadixRouter()
        r.add_route("GET", "/", _handler)
        assert r.resolve("GET", "/")[0] is _handler


# --- RadixRouter: metadata ---

class TestMetadata:
    def test_metadata_returned(self):
        r = RadixRouter()
        meta = {"tags": ["users"], "summary": "List users"}
        r.add_route("GET", "/users", _handler, meta)
        result = r.resolve("GET", "/users")
        assert result[2] == meta

    def test_default_metadata_empty(self):
        r = RadixRouter()
        r.add_route("GET", "/users", _handler)
        assert r.resolve("GET", "/users")[2] == {}


# --- FasterRouter ---

class TestFasterRouter:
    def test_prefix_applied(self):
        router = FasterRouter(prefix="/api/v1")

        @router.get("/users")
        def list_users():
            pass

        assert len(router.routes) == 1
        assert router.routes[0]["path"] == "/api/v1/users"
        assert router.routes[0]["method"] == "GET"

    def test_tags_merged(self):
        router = FasterRouter(prefix="/api", tags=["api"])

        @router.get("/items", tags=["items"])
        def list_items():
            pass

        assert router.routes[0]["tags"] == ["api", "items"]

    def test_all_methods(self):
        router = FasterRouter()

        @router.get("/a")
        def a(): pass

        @router.post("/b")
        def b(): pass

        @router.put("/c")
        def c(): pass

        @router.delete("/d")
        def d(): pass

        @router.patch("/e")
        def e(): pass

        methods = [r["method"] for r in router.routes]
        assert methods == ["GET", "POST", "PUT", "DELETE", "PATCH"]

    def test_decorator_metadata(self):
        router = FasterRouter()

        @router.post("/users", summary="Create", status_code=201, deprecated=True)
        def create():
            pass

        route = router.routes[0]
        assert route["summary"] == "Create"
        assert route["status_code"] == 201
        assert route["deprecated"] is True
