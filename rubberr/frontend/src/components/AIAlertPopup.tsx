import { useState, useEffect } from 'react';
import { Sparkles, X, Check, Loader2, Calendar, MapPin, Trophy } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface EventDetail {
    name: string;
    rating_limit?: number;
    fee?: number;
    competitiveness?: string;
}

interface AIAlert {
    id: number;
    type: string;
    content: {
        title: string;
        date: string;
        location: string;
        recommendation: {
            tournament: string;
            recommended_events: EventDetail[];
        };
    };
    created_at: string;
}


export default function AIAlertPopup() {
    const [alerts, setAlerts] = useState<AIAlert[]>([]);
    const [currentAlert, setCurrentAlert] = useState<AIAlert | null>(null);
    const [loading, setLoading] = useState(false);
    const [signedUp, setSignedUp] = useState(false);

    useEffect(() => {
        const fetchAlerts = async () => {
            try {
                const res = await fetch(`${API_URL}/notifications`);
                const data = await res.json();
                if (data.length > 0) {
                    setAlerts(data);
                    setCurrentAlert(data[0]);
                }
            } catch (err) {
                console.error("Failed to fetch alerts:", err);
            }
        };

        fetchAlerts();
        const interval = setInterval(fetchAlerts, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    const handleDismiss = async () => {
        if (!currentAlert) return;
        try {
            await fetch(`${API_URL}/notifications/${currentAlert.id}/read`, { method: 'POST' });
            const remaining = alerts.filter(a => a.id !== currentAlert.id);
            setAlerts(remaining);
            setCurrentAlert(remaining.length > 0 ? remaining[0] : null);
        } catch (err) {
            console.error("Failed to dismiss alert:", err);
        }
    };

    const handleSignup = async () => {
        if (!currentAlert) return;
        setLoading(true);
        try {
            const eventNames = currentAlert.content.recommendation?.recommended_events?.map((e: any) => typeof e === 'string' ? e : e.name) || [];
            const response = await fetch(`${API_URL}/tournaments/signup?tournament_title=${encodeURIComponent(currentAlert.content.title)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(eventNames)
            });
            const data = await response.json();
            if (data.status === 'success') {
                setSignedUp(true);
                setTimeout(handleDismiss, 2000); // Auto-dismiss after success
            } else {
                alert(`Signup failed: ${data.message}`);
                setLoading(false);
            }
        } catch (err) {
            console.error("Signup error:", err);
            alert("Failed to trigger AI signup.");
            setLoading(false);
        }
    };

    if (!currentAlert) return null;

    return (
        <AnimatePresence>
            <motion.div 
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                className="fixed bottom-8 right-8 z-[500] w-96"
            >
                <div className="bg-[#111] border-2 border-purple-500/50 rounded-2xl shadow-2xl overflow-hidden shadow-purple-900/40">
                    {/* Header */}
                    <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-4 py-3 flex justify-between items-center">
                        <div className="flex items-center gap-2 text-white font-bold text-sm">
                            <Sparkles size={16} />
                            AI OPPORTUNITY DETECTED
                        </div>
                        <button onClick={handleDismiss} className="text-white/70 hover:text-white transition-colors">
                            <X size={18} />
                        </button>
                    </div>

                    {/* Content */}
                    <div className="p-5">
                        <div className="mb-4">
                            <h3 className="text-white font-bold text-lg leading-tight mb-2">
                                {currentAlert.content.title}
                            </h3>
                            <div className="space-y-1">
                                <div className="flex items-center gap-2 text-xs text-gray-400">
                                    <Calendar size={12} /> {currentAlert.content.date}
                                </div>
                                <div className="flex items-center gap-2 text-xs text-gray-400">
                                    <MapPin size={12} /> {currentAlert.content.location}
                                </div>
                            </div>
                        </div>


                        <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl p-3 mb-5">
                            <div className="flex items-center gap-2 text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-2">
                                <Trophy size={10} /> AI Recommended Events
                            </div>
                            {currentAlert.content.recommendation?.recommended_events?.length > 0 && (
                                <div className="space-y-2">
                                    {currentAlert.content.recommendation.recommended_events.map((event: any, i: number) => {
                                        const isString = typeof event === 'string';
                                        const name = isString ? event : event.name;
                                        const fee = !isString ? event.fee : null;
                                        const limit = !isString ? event.rating_limit : null;
                                        const comp = !isString ? event.competitiveness : "Recommended";

                                        return (
                                            <div key={i} className="bg-black/30 rounded-lg p-2.5 border border-purple-500/20">
                                                <div className="flex justify-between items-start mb-1">
                                                    <h4 className="text-white font-bold text-sm">{name}</h4>
                                                    {comp && (
                                                        <span className="px-2 py-0.5 rounded-full bg-purple-500/30 text-[9px] text-purple-300 border border-purple-500/40">
                                                            {comp}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex gap-3 text-xs text-gray-400">
                                                    {fee && (
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-green-400">$</span>
                                                            <span>{fee}</span>
                                                        </div>
                                                    )}
                                                    {limit && (
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-purple-400">•</span>
                                                            <span>Under {limit} rating</span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>


                        {/* Actions */}
                        <div className="flex gap-3">
                            <button 
                                onClick={handleSignup}
                                disabled={loading || signedUp}
                                className={`
                                    flex-1 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all
                                    ${signedUp 
                                        ? 'bg-green-500 text-white' 
                                        : 'bg-white text-black hover:bg-gray-200'
                                    }
                                    ${loading ? 'opacity-70 cursor-not-allowed' : ''}
                                `}
                            >
                                {loading ? <Loader2 size={16} className="animate-spin" /> : signedUp ? <Check size={16} /> : <Sparkles size={16} />}
                                {loading ? 'Processing...' : signedUp ? 'Signed Up!' : 'Sign Up with AI'}
                            </button>
                            <button 
                                onClick={handleDismiss}
                                className="px-4 py-3 rounded-xl bg-[#222] text-gray-400 font-bold text-sm hover:bg-[#333] transition-all"
                            >
                                Later
                            </button>
                        </div>
                    </div>

                    {/* Footer Info */}
                    <div className="bg-[#1a1a1a] px-5 py-2 border-t border-[#333] flex justify-between items-center">
                         <span className="text-[10px] text-gray-500">
                            Detection Mode: Active
                         </span>
                         {alerts.length > 1 && (
                            <span className="text-[10px] text-purple-400 font-bold">
                                {alerts.length - 1} more alert{alerts.length > 2 ? 's' : ''}
                            </span>
                         )}
                    </div>
                </div>
            </motion.div>
        </AnimatePresence>
    );
}
