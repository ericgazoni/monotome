from collections import defaultdict


def topological_sort(pages):
    graph = defaultdict(set)
    page_by_id = {page.id: page for page in pages}

    for page in pages:
        if not page.requires:
            continue
        if isinstance(page.requires, str):
            requires = [page.requires]
        else:
            requires = page.requires
        for required_file in requires:
            graph[required_file].add(page.id)

    visited = set()
    temp = set()
    result = []

    def visit(node_id):
        if node_id in visited:
            return
        if node_id in temp:
            raise ValueError(f"Cycle detected at {node_id}")
        temp.add(node_id)
        for dependent in sorted(graph.get(node_id, [])):
            visit(dependent)
        temp.remove(node_id)
        visited.add(node_id)
        if node_id in page_by_id:
            result.append(page_by_id[node_id])

    for page_id in page_by_id:
        visit(page_id)

    return result[::-1]
