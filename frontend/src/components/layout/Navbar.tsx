import React, { useState, useEffect } from 'react';
import { Link, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { Sparkles, Compass, Layers, Menu, X, Activity } from 'lucide-react';
import { getHealthStatus } from '../../services/searchApi';

export const Navbar: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [healthStatus, setHealthStatus] = useState<'healthy' | 'degraded' | 'offline' | 'checking'>('checking');
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let isMounted = true;
    async function checkHealth() {
      try {
        const res = await getHealthStatus();
        if (isMounted) {
          setHealthStatus(res.status === 'healthy' ? 'healthy' : 'degraded');
        }
      } catch {
        if (isMounted) {
          setHealthStatus('offline');
        }
      }
    }
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const navLinks = [
    { to: '/', label: 'Home', icon: Compass },
    { to: '/search', label: 'Explore Search', icon: Sparkles },
    { to: '/outfit', label: 'Outfit Studio', icon: Layers },
  ];

  return (
    <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-sand-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <Link to="/" className="flex items-center gap-2 group">
          <span className="font-serif text-2xl font-light tracking-widest text-brand-900 group-hover:text-black transition-colors">
            ATELIER
          </span>
          <span className="hidden sm:inline-block text-[10px] font-sans uppercase tracking-widest px-2 py-0.5 rounded bg-sand-100 text-sand-600 border border-sand-200">
            AI Fashion
          </span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 text-xs uppercase tracking-widest font-medium transition-colors ${
                    isActive ? 'text-brand-900 font-semibold' : 'text-sand-600 hover:text-brand-900'
                  }`
                }
              >
                <Icon className="w-3.5 h-3.5" />
                {link.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Right Status & Actions */}
        <div className="hidden sm:flex items-center gap-4">
          <div
            className="flex items-center gap-1.5 text-[11px] text-sand-600 px-2.5 py-1 rounded-full bg-sand-50 border border-sand-200"
            title={`Backend Service: ${healthStatus}`}
          >
            <Activity className="w-3 h-3 text-sand-500" />
            <span
              className={`w-2 h-2 rounded-full ${
                healthStatus === 'healthy'
                  ? 'bg-emerald-500 animate-pulse'
                  : healthStatus === 'degraded'
                  ? 'bg-amber-500'
                  : 'bg-red-400'
              }`}
            />
            <span className="capitalize">{healthStatus}</span>
          </div>

          {location.pathname !== '/outfit' && (
            <button
              onClick={() => navigate('/outfit')}
              className="text-xs uppercase tracking-wider font-semibold bg-brand-900 text-white hover:bg-black px-4 py-2 rounded-full transition-all shadow-sm"
            >
              Compose Outfit
            </button>
          )}
        </div>

        {/* Mobile menu toggle */}
        <div className="flex md:hidden items-center gap-3">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 text-sand-700 hover:text-brand-900 focus:outline-none"
            aria-label="Toggle Navigation Menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-sand-200 bg-white px-4 pt-3 pb-5 space-y-3">
          {navLinks.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg font-medium ${
                    isActive ? 'bg-sand-100 text-brand-900 font-semibold' : 'text-sand-700 hover:bg-sand-50'
                  }`
                }
              >
                <Icon className="w-4 h-4 text-sand-500" />
                {link.label}
              </NavLink>
            );
          })}
          <div className="pt-2 border-t border-sand-100 flex items-center justify-between text-xs text-sand-600 px-3">
            <span>FastAPI Microservice</span>
            <span className="flex items-center gap-1.5 capitalize font-medium">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthStatus === 'healthy' ? 'bg-emerald-500' : 'bg-red-400'
                }`}
              />
              {healthStatus}
            </span>
          </div>
        </div>
      )}
    </header>
  );
};
