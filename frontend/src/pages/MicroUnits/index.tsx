import AdminView from "./AdminView";

export default function MicroUnitsPage() {
  // For now, default to AdminView.
  // In the future, check auth role and show AdminView for ADMIN or redirect to PocDashboardView for POC.
  return <AdminView />;
}
