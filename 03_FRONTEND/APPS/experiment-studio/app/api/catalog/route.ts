import { workspaceDatasets, workspaceSummary } from '../../workspace-data';

export async function GET() {
  return Response.json({
    contract: 'ax-experiment-catalog/v1',
    workspace: '8-AGENT',
    summary: workspaceSummary,
    datasets: workspaceDatasets,
  });
}
