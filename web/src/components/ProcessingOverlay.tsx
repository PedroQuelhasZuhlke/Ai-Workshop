export default function ProcessingOverlay({ message }: { message: string }) {
  return (
    <div className="processing-overlay" role="alert" aria-busy="true">
      <div className="processing-box">
        <div className="spinner" />
        <p>{message}</p>
      </div>
    </div>
  );
}
