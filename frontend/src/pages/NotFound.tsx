import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Compass, ArrowLeft } from 'lucide-react';
import { Button } from '../components/common/Button';

export const NotFound: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4 sm:px-6 lg:px-8 py-16">
      <div className="text-center max-w-md space-y-6">
        <span className="font-serif text-7xl font-extralight text-sand-400 tracking-wider">
          404
        </span>

        <h1 className="font-serif text-3xl font-light text-brand-900">Page Not Found</h1>

        <p className="text-sand-600 text-sm leading-relaxed">
          The fashion discovery runway you are searching for does not exist or may have been moved.
        </p>

        <div className="pt-4 flex items-center justify-center gap-4">
          <Button
            variant="outline"
            size="md"
            onClick={() => navigate(-1)}
            icon={<ArrowLeft className="w-4 h-4" />}
          >
            Go Back
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => navigate('/')}
            icon={<Compass className="w-4 h-4" />}
          >
            Atelier Home
          </Button>
        </div>
      </div>
    </div>
  );
};
