import React, { useState, useEffect } from 'react';
import { Link, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { Sparkles, Compass, Menu, X, Activity, Search } from 'lucide-react';
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
    { to: '/search', label: 'Explore Catalog', icon: Sparkles },
  ];

  return (
    <header className="sticky top-0 z-40 bg-white/85 backdrop-blur-md border-b border-sand-200/80 transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 flex items-center justify-between">
        {/* Brand with Haute Couture Aesthetic */}
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-full bg-brand-900 text-white flex items-center justify-center font-serif text-sm tracking-tighter shadow-xs group-hover:scale-105 transition-transform duration-300">
            A
          </div>
          <div className="flex flex-col">
            <span className="font-serif text-2xl font-normal tracking-[0.2em] text-brand-900 group-hover:text-black transition-colors">
              ATELIER
            </span>
            <span className="text-[9px] uppercase tracking-[0.25em] text-accent-700 font-medium">
              Neural Fashion Intelligence
            </span>
          </div>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-10">
          {navLinks.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `relative flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-medium py-2 transition-all ${
                    isActive
                      ? 'text-brand-900 font-semibold'
                      : 'text-sand-600 hover:text-brand-900'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-accent-600' : 'text-sand-400'}`} />
                    <span>{link.label}</span>
                    {isActive && (
                      <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-900 rounded-full" />
                    )}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Right Status & Actions */}
        <div className="hidden sm:flex items-center gap-4">
          <div
            className="flex items-center gap-2 text-[11px] text-sand-600 px-3 py-1.5 rounded-full bg-sand-50/80 border border-sand-200/90 shadow-2xs"
            title={`Backend Engine Status: ${healthStatus}`}
          >
            <Activity className="w-3 h-3 text-sand-400" />
            <span
              className={`w-2 h-2 rounded-full ${
                healthStatus === 'healthy'
                  ? 'bg-emerald-500 ring-2 ring-emerald-200 animate-pulse'
                  : healthStatus === 'degraded'
                  ? 'bg-amber-500'
                  : 'bg-red-400'
              }`}
            />
            <span className="capitalize font-medium text-sand-700">{healthStatus}</span>
          </div>

          {location.pathname !== '/search' && (
            <button
              onClick={() => navigate('/search')}
              className="inline-flex items-center gap-2 text-xs uppercase tracking-wider font-semibold bg-brand-900 text-white hover:bg-black px-4.5 py-2.5 rounded-full transition-all duration-300 shadow-sm hover:shadow-md hover:-translate-y-0.5 active:scale-95"
            >
              <Search className="w-3.5 h-3.5 text-accent-300" />
              <span>Search Catalog</span>
            </button>
          )}
        </div>

        {/* Mobile menu toggle */}
        <div className="flex md:hidden items-center gap-3">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 text-sand-700 hover:text-brand-900 focus:outline-none rounded-lg"
            aria-label="Toggle Navigation Menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-sand-200 bg-white/95 backdrop-blur-md px-5 pt-3 pb-6 space-y-3 shadow-lg">
          {navLinks.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 text-sm rounded-xl font-medium transition-colors ${
                    isActive
                      ? 'bg-sand-100 text-brand-900 font-semibold'
                      : 'text-sand-700 hover:bg-sand-50'
                  }`
                }
              >
                <Icon className="w-4 h-4 text-sand-500" />
                {link.label}
              </NavLink>
            );
          })}
          <div className="pt-3 border-t border-sand-100 flex items-center justify-between text-xs text-sand-600 px-3">
            <span>FastAPI Retrieval Engine</span>
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
