import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { t } from '../i18n';

export default function BackButton() {
  const navigate = useNavigate();
  return (
    <button
      className="btn-back"
      onClick={() => navigate(-1)}
      title={t('BackButton.go_back')}
    >
      <ArrowLeft size={20} />
    </button>
  );
}
