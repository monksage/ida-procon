"""
ContourBuilder: creates procon directories and graph.json files.
"""

import json
import os
from pathlib import Path

from models.contour import ContourSubmit
from services.registry import Registry
from services.write_queue import WriteQueue, WriteOp


class ContourBuilder:
    def __init__(self, registry: Registry, write_queue: WriteQueue):
        self.registry = registry
        self.wq = write_queue

    def submit(self, contour: ContourSubmit) -> bool:
        mod = self.registry.get_module(contour.module)
        if mod is None:
            return False

        procon_dir = mod.path / "procon" / contour.name
        graph_data = {
            "name": contour.name,
            "soldier": contour.soldier,
            "entry": contour.entry,
            "module": contour.module,
            "nodes": {k: v.model_dump() for k, v in contour.nodes.items()},
            "edges": contour.edges,
            "external_deps": contour.external_deps,
            "summary": contour.summary,
        }

        def _do_submit():
            os.makedirs(procon_dir, exist_ok=True)
            graph_path = procon_dir / "graph.json"
            with open(graph_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2, ensure_ascii=False)

            # update coverage for all nodes
            for func_name, node_info in contour.nodes.items():
                cov_node = mod.get_coverage_node(func_name)
                if cov_node is None:
                    continue
                if node_info.role == "micro":
                    # micro stays shared, just track partof
                    if contour.name not in cov_node.get("partof", []):
                        cov_node.setdefault("partof", []).append(contour.name)
                else:
                    cov_node["status"] = "resolved"
                    if contour.name not in cov_node.get("partof", []):
                        cov_node.setdefault("partof", []).append(contour.name)

            # add edges to coverage
            for edge in contour.edges:
                if edge not in mod.coverage.get("edges", []):
                    mod.coverage.setdefault("edges", []).append(edge)

        self.wq.enqueue(WriteOp(
            module=contour.module,
            op_type="submit_contour",
            func_name=contour.name,
            action=_do_submit,
        ))
        return True
