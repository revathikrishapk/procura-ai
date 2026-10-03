from fastapi import HTTPException, Request


def get_workflow_graph(request: Request):
    graph = getattr(request.app.state, "procurement_graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="Procurement workflow is starting.")
    return graph
