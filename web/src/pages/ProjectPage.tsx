import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Project, Run } from "../api/types";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function refresh() {
    if (!projectId) return;
    try {
      const [p, r] = await Promise.all([api.getProject(projectId), api.listRuns(projectId)]);
      setProject(p);
      setRuns(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function upload() {
    if (!projectId || !fileInput.current?.files?.[0]) return;
    setError(null);
    try {
      await api.uploadRun(projectId, fileInput.current.files[0]);
      fileInput.current.value = "";
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <div className="card">
        <h2>{project?.name ?? "Project"}</h2>
        <p className="muted">Your role: {project?.role}</p>
        <h4>Upload a BOM</h4>
        <div className="field-row">
          <input type="file" ref={fileInput} accept=".csv,.xlsx,.xls" />
          <button onClick={upload}>Upload</button>
        </div>
        {error && <p className="error-text">{error}</p>}
      </div>
      <div className="card">
        <h3>Runs</h3>
        {runs === null && <p>Loading...</p>}
        {runs && runs.length === 0 && <p className="muted">No runs yet -- upload a BOM above.</p>}
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Status</th>
              <th>Board qty</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runs?.map((r) => (
              <tr key={r.id}>
                <td>{r.source_filename}</td>
                <td>{r.status}</td>
                <td>{r.board_quantity ?? "-"}</td>
                <td>{new Date(r.created_at).toLocaleString()}</td>
                <td>
                  <Link to={`/projects/${projectId}/runs/${r.id}`}>Open</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
