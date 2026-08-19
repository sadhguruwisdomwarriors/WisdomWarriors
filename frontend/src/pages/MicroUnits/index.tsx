import { useQuery } from "@tanstack/react-query";
import { fetchMyUnit } from "../../api/microUnits";
import type { User } from "../../api/auth";
import AdminView from "./AdminView";
import PocDashboardView from "./PocDashboardView";

interface MicroUnitsPageProps {
  currentUser?: User | null;
}

export default function MicroUnitsPage({ currentUser }: MicroUnitsPageProps) {
  const isPoc = currentUser?.role === "POC";

  const { data: myUnit, isLoading, error } = useQuery({
    queryKey: ["myUnit"],
    queryFn: fetchMyUnit,
    enabled: isPoc,
  });

  if (isPoc) {
    if (isLoading) {
      return <div className="p-6 text-gray-400">Loading your Micro Unit dashboard...</div>;
    }
    if (error || !myUnit?.id) {
      return (
        <div className="p-8 max-w-lg mx-auto mt-12 bg-gray-900 border border-gray-800 rounded-2xl text-center">
          <div className="w-12 h-12 rounded-full bg-purple-950/60 border border-purple-800 text-purple-400 flex items-center justify-center mx-auto mb-4 text-xl">
            📋
          </div>
          <h2 className="text-xl font-bold text-white mb-2">No Micro Unit Assigned Yet</h2>
          <p className="text-gray-400 text-sm">
            Your account ({currentUser?.email}) has not been assigned to a Micro Unit yet. Please ask an Admin to assign your account in the Admin Overview.
          </p>
        </div>
      );
    }
    return <PocDashboardView unitIdOverride={myUnit.id} />;
  }

  return <AdminView />;
}
