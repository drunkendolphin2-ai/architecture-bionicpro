import React, { useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

interface ReportRow {
  date: string;
  full_name: string;
  model: string;
  events_total: number;
  avg_response_ms: number;
  p95_response_ms: number;
  avg_signal_quality: number;
  min_battery_pct: number;
  errors_total: number;
}

interface Report {
  user_id: string;
  username: string;
  requested: { from: string; to: string };
  available_through: string | null;
  truncated: boolean;
  rows: ReportRow[];
  message?: string;
}

const isoDaysAgo = (days: number): string =>
  new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(30));
  const [dateTo, setDateTo] = useState(isoDaysAgo(0));

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    setReport(null);

    try {
      // access token живёт минуты; обновляем, если осталось меньше 30 секунд
      await keycloak.updateToken(30);

      const query = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      const response = await fetch(
        `${process.env.REACT_APP_API_URL}/reports?${query}`,
        { headers: { Authorization: `Bearer ${keycloak.token}` } }
      );

      if (response.status === 401) {
        throw new Error('Сессия истекла, войдите заново');
      }
      if (response.status === 403) {
        throw new Error('Нет доступа к отчётам: у пользователя нет роли prothetic_user');
      }
      if (!response.ok) {
        throw new Error(`Сервис отчётов вернул ${response.status}`);
      }

      setReport(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось получить отчёт');
    } finally {
      setLoading(false);
    }
  };

  const saveToFile = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `report-${report.username}-${dateFrom}_${dateTo}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (!initialized) {
    return <div className="p-8">Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-5xl mx-auto p-8 bg-white rounded-lg shadow-md">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold">Отчёт о работе протеза</h1>
            <p className="text-sm text-gray-500 mt-1">
              {keycloak.tokenParsed?.preferred_username as string}
            </p>
          </div>
          <button
            onClick={() => keycloak.logout()}
            className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            Выйти
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-4 mb-6">
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">С</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1"
            />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">По</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1"
            />
          </label>

          <button
            onClick={loadReport}
            disabled={loading}
            className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
              loading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            {loading ? 'Формируется...' : 'Получить отчёт'}
          </button>

          {report && report.rows.length > 0 && (
            <button
              onClick={saveToFile}
              className="px-4 py-2 border border-blue-500 text-blue-600 rounded hover:bg-blue-50"
            >
              Скачать
            </button>
          )}
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {report?.truncated && (
          <div className="mb-4 p-4 bg-amber-100 text-amber-800 rounded text-sm">
            Данные обработаны по {report.available_through ?? '—'}. Более поздний
            период ещё не попал в витрину.
          </div>
        )}

        {report && report.rows.length === 0 && !error && (
          <div className="p-4 bg-gray-50 text-gray-600 rounded">
            {report.message ?? 'За выбранный период данных нет'}
          </div>
        )}

        {report && report.rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-600 border-b">
                  <th className="py-2 pr-4">Дата</th>
                  <th className="py-2 pr-4">Модель</th>
                  <th className="py-2 pr-4">Событий</th>
                  <th className="py-2 pr-4">Отклик, мс</th>
                  <th className="py-2 pr-4">p95, мс</th>
                  <th className="py-2 pr-4">Качество сигнала</th>
                  <th className="py-2 pr-4">Мин. заряд, %</th>
                  <th className="py-2">Ошибок</th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((row) => (
                  <tr key={row.date} className="border-b last:border-0">
                    <td className="py-2 pr-4">{row.date}</td>
                    <td className="py-2 pr-4">{row.model}</td>
                    <td className="py-2 pr-4">{row.events_total}</td>
                    <td className="py-2 pr-4">{row.avg_response_ms}</td>
                    <td className="py-2 pr-4">{row.p95_response_ms}</td>
                    <td className="py-2 pr-4">{row.avg_signal_quality}</td>
                    <td className="py-2 pr-4">{row.min_battery_pct}</td>
                    <td className="py-2">{row.errors_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
