import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Calculator, UserCheck } from "lucide-react";
import { fetchMicroUnits } from "../../api/microUnits";
import { getMe, getToken, type User } from "../../api/auth";
import { Link } from "react-router-dom";
import CreateUnitModal from "./CreateUnitModal";
import AssignPocModal from "./AssignPocModal";
import CalculateMetricsModal from "./CalculateMetricsModal";
import CreateUserModal from "./CreateUserModal";

export default function AdminView() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [showCalcModal, setShowCalcModal] = useState(false);
  const [showUserModal, setShowUserModal] = useState(false);
  const [selectedUnitId, setSelectedUnitId] = useState<number | undefined>();
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  const loadUser = async () => {
    if (getToken()) {
      try {
        const user = await getMe();
        setCurrentUser(user);
      } catch {
        setCurrentUser(null);
      }
    } else {
      setCurrentUser(null);
    }
  };

  useEffect(() => {
    loadUser();
  }, []);

  const { data: microUnits = [], isLoading, error } = useQuery({
    queryKey: ["microUnits"],
    queryFn: fetchMicroUnits,
  });

  const handleAssignPoc = (unitId?: number) => {
    setSelectedUnitId(unitId);
    setShowAssignModal(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Micro Units Overview</h1>
          {currentUser && (
            <p className="text-xs text-gray-400 mt-1">
              Logged in as <span className="text-purple-300 font-semibold">{currentUser.full_name}</span> ({currentUser.email}) • <span className="bg-purple-900/50 text-purple-300 px-1.5 py-0.5 rounded text-[11px] border border-purple-800">{currentUser.role}</span>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setShowUserModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors border border-gray-700 text-xs sm:text-sm font-medium whitespace-nowrap shadow-sm"
          >
            <UserCheck size={15} />
            + Create User / POC
          </button>
          <button
            onClick={() => setShowCalcModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors border border-gray-700 text-xs sm:text-sm font-medium whitespace-nowrap shadow-sm"
          >
            <Calculator size={15} />
            Calculate Monthly Metrics
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-purple-700 hover:bg-purple-600 text-white rounded-lg transition-colors text-xs sm:text-sm font-medium whitespace-nowrap shadow-sm shadow-purple-900/40"
          >
            <Plus size={15} />
            Create Micro Unit
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading micro units...</div>
      ) : error ? (
        <div className="text-red-400">Error loading micro units.</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {microUnits.map((unit) => {
            const pocDisplayName = unit.poc_name || unit.poc?.full_name;
            return (
            <div key={unit.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col hover:border-gray-700 transition-colors">
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-bold text-white text-lg">{unit.name}</h3>
                <span className="bg-purple-900/50 text-purple-300 text-xs px-2 py-1 rounded-full border border-purple-800">
                  ID: {unit.unit_number}
                </span>
              </div>
              
              <div className="text-sm mb-4">
                {pocDisplayName ? (
                  <span className="text-gray-300">POC: <span className="font-medium text-purple-300">{pocDisplayName}</span></span>
                ) : (
                  <span className="text-gray-500 italic">No POC assigned</span>
                )}
              </div>

              <div className="flex-1 mb-4">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Channels ({unit.channels.length})</h4>
                <ul className="space-y-2">
                  {unit.channels.slice(0, 5).map(channel => (
                    <li key={channel.id} className="flex items-center gap-2 text-sm text-gray-300">
                      <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
                          <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                          <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
                        </svg>
                      </div>
                      <span className="truncate" title={channel.username}>@{channel.username}</span>
                    </li>
                  ))}
                  {unit.channels.length > 5 && (
                    <li className="text-xs text-gray-500 italic pl-7">
                      +{unit.channels.length - 5} more...
                    </li>
                  )}
                  {unit.channels.length === 0 && (
                    <li className="text-sm text-gray-600 italic">No channels added.</li>
                  )}
                </ul>
              </div>

              <div className="grid grid-cols-3 gap-2 mt-auto pt-4 border-t border-gray-800">
                <button 
                  className="px-2 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors"
                  onClick={() => alert('Edit unit functionality not implemented yet')}
                >
                  Edit
                </button>
                <button 
                  className="px-2 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors"
                  onClick={() => handleAssignPoc(unit.id)}
                >
                  Assign POC
                </button>
                <Link 
                  to={`/micro-units/${unit.id}`}
                  className="px-2 py-1.5 bg-purple-900/40 hover:bg-purple-800/60 text-purple-300 rounded text-xs text-center transition-colors border border-purple-800/30"
                >
                  Dashboard
                </Link>
              </div>
            </div>
            );
          })}
        </div>
      )}

      {showCreateModal && <CreateUnitModal onClose={() => setShowCreateModal(false)} />}
      {showUserModal && <CreateUserModal onClose={() => setShowUserModal(false)} />}
      {showAssignModal && (
        <AssignPocModal 
          onClose={() => {
            setShowAssignModal(false);
            setSelectedUnitId(undefined);
          }} 
          microUnits={microUnits}
          defaultUnitId={selectedUnitId}
        />
      )}
      {showCalcModal && <CalculateMetricsModal onClose={() => setShowCalcModal(false)} />}
    </div>
  );
}
