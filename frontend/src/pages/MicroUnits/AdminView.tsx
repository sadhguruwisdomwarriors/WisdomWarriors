import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Calculator, UserCheck, Bell } from "lucide-react";
import { clsx } from "clsx";
import { fetchMicroUnits, type MicroUnit } from "../../api/microUnits";
import { getMe, getToken, getPendingRegistrations, type User } from "../../api/auth";
import { Link } from "react-router-dom";
import CreateUnitModal from "./CreateUnitModal";
import AssignPocModal from "./AssignPocModal";
import CalculateMetricsModal from "./CalculateMetricsModal";
import CreateUserModal from "./CreateUserModal";
import ManageChannelsModal from "./ManageChannelsModal";
import PendingApprovalsModal from "./PendingApprovalsModal";

export default function AdminView() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [showCalcModal, setShowCalcModal] = useState(false);
  const [showUserModal, setShowUserModal] = useState(false);
  const [showPendingModal, setShowPendingModal] = useState(false);
  const [selectedUnitId, setSelectedUnitId] = useState<number | undefined>();
  const [channelModalUnit, setChannelModalUnit] = useState<MicroUnit | null>(null);
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

  const { data: pendingRegistrations = [] } = useQuery({
    queryKey: ["pendingRegistrations"],
    queryFn: getPendingRegistrations,
    refetchInterval: 30000,
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
            onClick={() => setShowPendingModal(true)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg transition-colors border text-xs sm:text-sm font-medium whitespace-nowrap shadow-sm ${
              pendingRegistrations.length > 0
                ? "bg-amber-950/70 hover:bg-amber-900/90 text-amber-200 border-amber-600/70"
                : "bg-gray-800 hover:bg-gray-700 text-gray-300 border-gray-700"
            }`}
          >
            <Bell size={15} className={pendingRegistrations.length > 0 ? "text-amber-400 fill-amber-400/20" : ""} />
            <span>Pending POCs</span>
            {pendingRegistrations.length > 0 && (
              <span className="bg-amber-500 text-black text-[10px] font-extrabold px-1.5 py-0.2 rounded-full">
                {pendingRegistrations.length}
              </span>
            )}
          </button>
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

      {/* Admin Notification Banner for Pending Registrations */}
      {pendingRegistrations.length > 0 && (
        <div className="bg-gradient-to-r from-amber-950/60 via-amber-900/30 to-gray-900 border border-amber-600/50 rounded-xl p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-md">
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 rounded-lg bg-amber-900/80 text-amber-300 border border-amber-600/60 flex items-center justify-center font-bold text-sm flex-shrink-0">
              🔔
            </span>
            <div>
              <div className="text-white font-bold text-sm flex items-center gap-2">
                <span>{pendingRegistrations.length} New POC Registration{pendingRegistrations.length > 1 ? "s" : ""} Pending Review</span>
              </div>
              <p className="text-xs text-amber-200/80 mt-0.5">
                Prospective POCs have registered on the website and are awaiting your approval to access their Micro Units.
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowPendingModal(true)}
            className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold rounded-lg transition-colors flex-shrink-0 shadow-sm"
          >
            Review & Approve Requests
          </button>
        </div>
      )}

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
                  {unit.channels.slice(0, 5).map(channel => {
                    const isYT = (channel.platform || "INSTAGRAM").toUpperCase() === "YOUTUBE";
                    return (
                      <li key={channel.id} className="flex items-center gap-2 text-sm text-gray-300">
                        {isYT ? (
                          <div className="w-5 h-5 rounded-full bg-red-600 flex items-center justify-center flex-shrink-0 shadow-sm shadow-red-900/40">
                            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="white">
                              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                            </svg>
                          </div>
                        ) : (
                          <div className="w-5 h-5 rounded-full overflow-hidden flex items-center justify-center flex-shrink-0">
                            <img src="/wisdom_warriors_logo.jpg" alt="Wisdom Warriors" className="w-full h-full object-cover rounded-full" />
                          </div>
                        )}
                        <span className="truncate" title={channel.channel_title || channel.username}>
                          {isYT ? (channel.channel_title || channel.username) : `@${channel.username}`}
                        </span>
                        {channel.creator_name && channel.creator_name !== channel.username && (
                          <span className="text-[11px] text-gray-500 truncate">({channel.creator_name})</span>
                        )}
                      </li>
                    );
                  })}
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
                  className={clsx(
                    "px-2 py-1.5 rounded text-xs transition-colors font-medium truncate text-center",
                    unit.channels.length === 0 
                      ? "bg-purple-950/60 hover:bg-purple-900/80 text-purple-300 border border-purple-800/40" 
                      : "bg-gray-800 hover:bg-gray-700 text-gray-300"
                  )}
                  onClick={() => setChannelModalUnit(unit)}
                  title={unit.channels.length === 0 ? "+ Add Channels" : "Edit Channels"}
                >
                  {unit.channels.length === 0 ? "+ Add Channels" : "Edit Channels"}
                </button>
                <button 
                  className={clsx(
                    "px-2 py-1.5 rounded text-xs transition-colors font-medium truncate text-center",
                    pocDisplayName 
                      ? "bg-gray-800 hover:bg-gray-700 text-purple-300" 
                      : "bg-gray-800 hover:bg-gray-700 text-gray-300"
                  )}
                  onClick={() => handleAssignPoc(unit.id)}
                  title={pocDisplayName ? "Re-assign POC" : "Assign POC"}
                >
                  {pocDisplayName ? "Re-assign POC" : "Assign POC"}
                </button>
                <Link 
                  to={`/micro-units/${unit.id}`}
                  className="px-2 py-1.5 bg-purple-900/40 hover:bg-purple-800/60 text-purple-300 rounded text-xs text-center transition-colors border border-purple-800/30 font-medium truncate"
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
      {channelModalUnit && (
        <ManageChannelsModal
          unit={microUnits.find(u => u.id === channelModalUnit.id) || channelModalUnit}
          onClose={() => setChannelModalUnit(null)}
        />
      )}
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
      {showPendingModal && (
        <PendingApprovalsModal
          microUnits={microUnits}
          onClose={() => setShowPendingModal(false)}
        />
      )}
    </div>
  );
}
