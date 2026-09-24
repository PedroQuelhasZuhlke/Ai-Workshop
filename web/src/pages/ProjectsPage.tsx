import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Project } from "../api/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function create() {
    if (!name.trim()) return;
    setError(null);
    try {
      await api.createProject(name.trim());
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div>
      <div className="card">
        <h2>Projects</h2>
        <div className="field-row">
          <input
            placeholder="New project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button onClick={create} disabled={!name.trim()}>
            Create project
          </button>
        </div>
        {error && <p className="error-text">{error}</p>}
      </div>
      <div className="card">
        {projects === null && <p>Loading...</p>}
        {projects && projects.length === 0 && <p className="muted">No projects yet.</p>}
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Your role</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {projects?.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.role}</td>
                <td>{new Date(p.created_at).toLocaleString()}</td>
                <td>
                  <Link to={`/projects/${p.id}`}>Open</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
