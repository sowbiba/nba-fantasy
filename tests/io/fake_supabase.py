"""Faux client supabase-py : chaînage minimal, pagination par range(),
journal des écritures dans `ops`. Suffisant pour tester SupabaseRepo."""


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self._range = None
        self._write = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, *a):
        return self

    def in_(self, *a):
        return self

    @property
    def not_(self):
        return self

    def gte(self, *a):
        return self

    def lte(self, *a):
        return self

    def lt(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def upsert(self, rows, on_conflict=None):
        self._write = ("upsert", self.table, len(rows), on_conflict)
        return self

    def insert(self, rows):
        n = len(rows) if isinstance(rows, list) else 1
        self._write = ("insert", self.table, n, None)
        return self

    def update(self, payload):
        self._write = ("update", self.table, payload, None)
        return self

    def delete(self):
        self._write = ("delete", self.table, None, None)
        return self

    def execute(self):
        if self._write:
            self.client.ops.append(self._write)
            if self._write[0] == "insert":
                return _Resp([{"id": 42}])
            return _Resp([])
        rows = self.client.tables.get(self.table, [])
        if self._range:
            start, end = self._range
            return _Resp(rows[start:end + 1])
        return _Resp(rows)


class FakeClient:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.ops = []

    def table(self, name):
        return _Query(self, name)
