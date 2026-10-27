"""Municode API client.

Municode hosts most Texas municipal codes (and many nationwide) behind a stable
JSON API. Verified live against City of Austin (clientId 1113, LDC productId 15303):
  - Clients/name?clientName=..&stateAbbr=..        -> ClientID
  - ClientContent/{clientId}                       -> products (codes) + productId
  - Jobs/latest/{productId}                        -> latest supplement jobId
  - codesToc?jobId=..&productId=..                 -> TOC roots
  - codesToc/children?jobId=..&nodeId=..&productId -> TOC children
  - CodesContent?jobId=..&nodeId=..&productId=..   -> Docs[] with HTML content
    (content is only populated when requesting a node inside its chunk group)
"""

import time
from dataclasses import dataclass

import httpx

API = "https://api.municode.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CivicLLM-POC"


@dataclass
class TocNode:
    id: str
    heading: str
    has_children: bool
    hierarchy: list[str]  # headings from root to this node, inclusive


@dataclass
class SectionDoc:
    node_id: str
    title: str
    html: str
    hierarchy: list[str]


class MunicodeClient:
    def __init__(self) -> None:
        self._http = httpx.Client(base_url=API, headers={"User-Agent": UA}, timeout=90)

    def resolve_product(
        self, client_name: str, state: str, product_name: str
    ) -> tuple[int, int, str]:
        """Returns (product_id, job_id, banner_text) for e.g. ("Austin", "TX",
        "Land Development Code"). banner_text is the latest job's supplement banner,
        e.g. "Codified through Ordinance No. …. (Supp. No. …)"."""
        client = self._get("/Clients/name", {"clientName": client_name, "stateAbbr": state})
        products = self._get(f"/ClientContent/{client['ClientID']}")["codes"]
        matches = [p for p in products if product_name.lower() in p["productName"].lower()]
        if not matches:
            names = [p["productName"] for p in products]
            raise LookupError(f"No product matching {product_name!r}; available: {names}")
        product_id = matches[0]["productId"]
        job = self._get(f"/Jobs/latest/{product_id}")
        return product_id, job["Id"], (job.get("BannerText") or "").strip()

    def toc_children(self, job_id: int, product_id: int, node: TocNode | None) -> list[TocNode]:
        if node is None:
            data = self._get("/codesToc", {"jobId": job_id, "productId": product_id})
            raw = data.get("Children") or []
            base: list[str] = []
        else:
            raw = self._get(
                "/codesToc/children",
                {"jobId": job_id, "nodeId": node.id, "productId": product_id},
            )
            base = node.hierarchy
        return [
            TocNode(
                id=n["Id"],
                heading=(n.get("Heading") or "").strip(),
                has_children=bool(n.get("HasChildren")),
                hierarchy=[*base, (n.get("Heading") or "").strip()],
            )
            for n in raw
        ]

    def content_docs(self, job_id: int, product_id: int, node_id: str) -> list[dict]:
        data = self._get(
            "/CodesContent", {"jobId": job_id, "nodeId": node_id, "productId": product_id}
        )
        return data.get("Docs") or []

    def _get(self, path: str, params: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                resp = self._http.get(path, params=params)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_error = e
                time.sleep(2**attempt)
        raise RuntimeError(f"Municode request failed after retries: {path}") from last_error


def walk_sections(
    client: MunicodeClient, job_id: int, product_id: int, root_node_ids: list[str]
) -> list[TocNode]:
    """DFS the TOC under the given roots; returns leaf nodes (sections) with hierarchy."""
    roots = client.toc_children(job_id, product_id, None)
    index = {n.id: n for n in roots}

    # Roots given in config may be deeper than TOC top level; resolve by walking down.
    frontier: list[TocNode] = []
    for root_id in root_node_ids:
        node = index.get(root_id) or _find_node(client, job_id, product_id, roots, root_id)
        if node is None:
            raise LookupError(f"TOC node not found: {root_id}")
        frontier.append(node)

    leaves: list[TocNode] = []
    while frontier:
        node = frontier.pop()
        if not node.has_children:
            leaves.append(node)
            continue
        frontier.extend(client.toc_children(job_id, product_id, node))
    return leaves


def _find_node(
    client: MunicodeClient, job_id: int, product_id: int, roots: list[TocNode], target_id: str
) -> TocNode | None:
    """Walk down the TOC toward target_id (node ids are path-prefixed, e.g.
    TIT25LADE_CH25-2ZO starts with its parent id TIT25LADE)."""
    frontier = list(roots)
    while frontier:
        node = frontier.pop()
        if node.id == target_id:
            return node
        if node.has_children and target_id.startswith(node.id):
            frontier.extend(client.toc_children(job_id, product_id, node))
    return None
