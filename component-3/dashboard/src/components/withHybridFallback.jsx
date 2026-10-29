import { useSession } from "../state/session.jsx";
import { Callout, PageHeader } from "./ui.jsx";

// A workflow page shows the Hybrid GPA run when one exists and the CRUD/behaviour flow has not produced its own run.
// With neither, the page keeps its own empty state and a short hint points at the GPA generation on Code Generation.
export function withHybridFallback(HybridView, ClassicPage, { crudRunExists, title, emptyInsteadOfClassic = false }) {
  return function WorkflowPage(props) {
    const { session } = useSession();
    if (crudRunExists(session)) return <ClassicPage {...props} />;
    if (session.hybrid?.run) return <HybridView {...props} />;
    if (emptyInsteadOfClassic) {
      return (
        <div className="page">
          <PageHeader title={title} />
          <Callout tone="info" title="Nothing generated yet">
            Generate the project first on the{" "}
            <button type="button" className="link-button" onClick={() => props.navigate?.("generation")}>Code Generation</button>{" "}
            page. This page then shows its results here in plain language.
          </Callout>
        </div>
      );
    }
    return (
      <>
        <div className="page">
          <Callout tone="info" title="Using the GPA project?">
            Generate it first on the{" "}
            <button type="button" className="link-button" onClick={() => props.navigate?.("generation")}>Code Generation</button>{" "}
            page. This page then shows its results here in plain language.
          </Callout>
        </div>
        <ClassicPage {...props} />
      </>
    );
  };
}
