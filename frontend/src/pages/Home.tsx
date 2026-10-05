import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Layers, ArrowRight, ShieldCheck, Zap, Compass } from 'lucide-react';
import { SearchBar } from '../components/common/SearchBar';
import { Button } from '../components/common/Button';

export const Home: React.FC = () => {
  const navigate = useNavigate();

  const handleSearch = (query: string) => {
    navigate(`/search?q=${encodeURIComponent(query)}`);
  };

  const curatedCollections = [
    {
      title: 'Cocktail & Evening',
      query: 'red cocktail dress',
      desc: 'Elegant silhouettes and structured silk for unforgettable nights',
      tag: 'Trending Now',
    },
    {
      title: 'Summer Resort Linen',
      query: 'oversized linen blazer for summer',
      desc: 'Breathable tailoring in natural stone and ecru tones',
      tag: 'Seasonal Edit',
    },
    {
      title: 'Athletic Luxury',
      query: 'black waterproof running shoes',
      desc: 'Technical performance sneakers with minimal styling',
      tag: 'Performance',
    },
    {
      title: 'Artisanal Leather',
      query: 'vintage leather crossbody bag',
      desc: 'Handcrafted leather accessories with vintage patina',
      tag: 'Curated Essentials',
    },
  ];

  return (
    <div className="space-y-24 pb-24">
      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-28 md:pt-28 md:pb-36 bg-gradient-to-b from-white via-sand-50/50 to-sand-50 border-b border-sand-200">
        {/* Subtle decorative circles */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-gradient-to-tr from-accent-100/40 via-sand-200/30 to-transparent blur-3xl -z-10 pointer-events-none" />

        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center space-y-8">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-sand-100/80 border border-sand-200 text-xs font-semibold uppercase tracking-widest text-brand-900 shadow-xs">
            <Sparkles className="w-3.5 h-3.5 text-accent-600 animate-pulse" />
            <span>Semantic Vector & Hybrid Retrieval Engine</span>
          </div>

          <h1 className="font-serif text-4xl sm:text-6xl md:text-7xl font-normal tracking-tight text-brand-900 leading-[1.1]">
            Search Fashion by <span className="italic font-light">Mood</span>,{' '}
            <span className="italic font-light">Style</span> & Context
          </h1>

          <p className="max-w-2xl mx-auto text-base sm:text-lg text-sand-600 leading-relaxed font-light">
            Go beyond simple keywords. Our neural index understands descriptive fashion queries,
            occasions, budgets, and harmonized cross-category ensembles across 24,000 catalog pieces.
          </p>

          {/* Main Semantic Search Input */}
          <div className="max-w-2xl mx-auto pt-2">
            <SearchBar
              placeholder="Try 'red cocktail dress' or 'oversized blazer for summer'..."
              onSearch={handleSearch}
              size="lg"
              showPills={true}
              examplePills={[
                'red cocktail dress',
                'summer linen blazer',
                'waterproof running shoes',
                'leather crossbody bag',
              ]}
            />
          </div>

          {/* Two prominent CTAs */}
          <div className="pt-6 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button
              variant="primary"
              size="lg"
              onClick={() => navigate('/search')}
              icon={<Compass className="w-4 h-4" />}
            >
              Explore Catalog Search
            </Button>
            <Button
              variant="outline"
              size="lg"
              onClick={() => navigate('/outfit')}
              icon={<Layers className="w-4 h-4 text-accent-600" />}
            >
              Outfit Recommendation Studio
            </Button>
          </div>
        </div>
      </section>

      {/* Outfit Studio Promo Feature Banner */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-gradient-to-br from-brand-900 via-brand-800 to-black text-white rounded-3xl p-8 sm:p-12 md:p-16 shadow-xl relative overflow-hidden">
          <div className="relative z-10 max-w-2xl space-y-6">
            <div className="inline-flex items-center gap-2 text-xs uppercase tracking-widest px-3 py-1 rounded-full bg-white/10 text-sand-200 border border-white/10 backdrop-blur-xs">
              <Layers className="w-3.5 h-3.5 text-accent-300" />
              Generative Stylist
            </div>

            <h2 className="font-serif text-3xl sm:text-5xl font-light leading-tight">
              Looking for a Complete Coordinated Look?
            </h2>

            <p className="text-sand-300 text-sm sm:text-base leading-relaxed">
              Describe your occasion or budget—for instance,{' '}
              <span className="text-white italic">
                &quot;cocktail party outfit for women under $100&quot;
              </span>
              . Our microservice retrieves harmonized tops, bottoms, footwear, and accessories that
              complement each other while satisfying strict budget limits.
            </p>

            <div className="pt-2">
              <Button
                variant="secondary"
                size="lg"
                onClick={() =>
                  navigate(
                    `/outfit?q=${encodeURIComponent('cocktail party outfit for women under $100')}`
                  )
                }
                icon={<ArrowRight className="w-4 h-4" />}
              >
                Launch Outfit Recommender
              </Button>
            </div>
          </div>

          {/* Aesthetic background glow */}
          <div className="absolute right-0 bottom-0 w-96 h-96 bg-accent-600/20 rounded-full blur-3xl pointer-events-none" />
        </div>
      </section>

      {/* Curated Semantic Lookbooks */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-sand-200 pb-4">
          <div>
            <span className="text-xs uppercase tracking-widest font-semibold text-accent-700">
              Inspiration & Intent
            </span>
            <h2 className="font-serif text-3xl font-light text-brand-900 mt-1">
              Curated Semantic Prompts
            </h2>
          </div>
          <button
            onClick={() => navigate('/search')}
            className="text-xs uppercase tracking-widest font-semibold text-brand-900 hover:text-black flex items-center gap-1.5 group"
          >
            <span>Browse Full Catalog</span>
            <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {curatedCollections.map((col, idx) => (
            <div
              key={idx}
              onClick={() => handleSearch(col.query)}
              className="group bg-white rounded-3xl p-6 border border-sand-200 shadow-subtle hover:shadow-card hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between cursor-pointer"
            >
              <div className="space-y-3">
                <span className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-sand-100 text-sand-700 border border-sand-200">
                  {col.tag}
                </span>
                <h3 className="font-serif text-xl text-brand-900 group-hover:text-black transition-colors">
                  {col.title}
                </h3>
                <p className="text-xs text-sand-500 leading-relaxed font-sans">{col.desc}</p>
              </div>

              <div className="pt-6 border-t border-sand-100 mt-6 flex items-center justify-between">
                <span className="text-xs font-mono text-sand-400">&ldquo;{col.query}&rdquo;</span>
                <span className="w-8 h-8 rounded-full bg-sand-100 group-hover:bg-brand-900 group-hover:text-white flex items-center justify-center transition-colors text-sand-600">
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Engineering & Retrieval Highlights */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-sand-100/60 rounded-3xl p-8 sm:p-12 border border-sand-200">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-2xl bg-white shadow-xs border border-sand-200 flex items-center justify-center text-accent-700 shrink-0">
                <Sparkles className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="font-serif text-lg text-brand-900">Dense + Sparse Hybrid</h4>
                <p className="text-xs text-sand-600 leading-relaxed">
                  Blends Sentence Transformer dense vector embeddings (FAISS) with BM25 Okapi lexical
                  scoring via Reciprocal Rank Fusion.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-2xl bg-white shadow-xs border border-sand-200 flex items-center justify-center text-accent-700 shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="font-serif text-lg text-brand-900">Deterministic Constraints</h4>
                <p className="text-xs text-sand-600 leading-relaxed">
                  Enforces strict hard filtering for gender, age group, slot compatibility, and budget
                  ceilings with circuit-breaker protection.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-2xl bg-white shadow-xs border border-sand-200 flex items-center justify-center text-accent-700 shrink-0">
                <Zap className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="font-serif text-lg text-brand-900">Low-Latency Microservice</h4>
                <p className="text-xs text-sand-600 leading-relaxed">
                  Sub-50ms hybrid retrieval across 24,000 pre-embedded apparel records with LRU query
                  caching.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
