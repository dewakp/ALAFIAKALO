import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export default function BackButton() {
  const navigate = useNavigate();
  return (
    <button
      className="btn-back"
      onClick={() => navigate(-1)}
      title="Go back"
    >
      <ArrowLeft size={20} />
    </button>
  );
}
