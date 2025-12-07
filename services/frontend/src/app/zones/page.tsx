'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { bookingService } from '@/lib/booking';
import { authService } from '@/lib/auth';
import { Zone, Place, Slot } from '@/types';

export default function ZonesPage() {
  const router = useRouter();
  const [zones, setZones] = useState<Zone[]>([]);
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [bookingSlot, setBookingSlot] = useState<number | null>(null);
  const [bookingError, setBookingError] = useState<string>('');
  const [bookingSuccess, setBookingSuccess] = useState<string>('');

  useEffect(() => {
    loadZones();
  }, []);

  const loadZones = async () => {
    try {
      const data = await bookingService.getZones();
      setZones(data.filter(z => z.is_active));
      setLoading(false);
    } catch (err) {
      setError('Ошибка загрузки зон');
      setLoading(false);
    }
  };

  const handleZoneSelect = async (zone: Zone) => {
    setSelectedZone(zone);
    setSelectedPlace(null);
    setSlots([]);
    
    try {
      const data = await bookingService.getPlacesByZone(zone.id);
      setPlaces(data.filter(p => p.is_active));
    } catch (err) {
      setError('Ошибка загрузки мест');
    }
  };

  const handlePlaceSelect = async (place: Place) => {
    setSelectedPlace(place);
    await loadSlots(place.id, selectedDate);
  };

  const loadSlots = async (placeId: number, date: string) => {
    try {
      const data = await bookingService.getSlots(placeId, date);
      setSlots(data);
    } catch (err) {
      setError('Ошибка загрузки слотов');
    }
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    if (selectedPlace) {
      loadSlots(selectedPlace.id, date);
    }
  };

  const handleBookSlot = async (slotId: number) => {
    if (!authService.isAuthenticated()) {
      router.push('/login');
      return;
    }

    setBookingSlot(slotId);
    setBookingError('');
    setBookingSuccess('');

    try {
      await bookingService.createBooking({ slot_id: slotId });
      setBookingSuccess('Бронирование успешно создано!');
      
      // Перезагружаем слоты
      if (selectedPlace) {
        await loadSlots(selectedPlace.id, selectedDate);
      }
      
      // Скрыть сообщение через 3 секунды
      setTimeout(() => setBookingSuccess(''), 3000);
    } catch (err: any) {
      setBookingError(err.response?.data?.detail || 'Ошибка создания бронирования');
    } finally {
      setBookingSlot(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-lg text-gray-600">Загрузка...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">
          Зоны и места для бронирования
        </h1>

        {error && (
          <div className="mb-4 rounded-md bg-red-50 p-4">
            <div className="text-sm text-red-700">{error}</div>
          </div>
        )}

        {bookingError && (
          <div className="mb-4 rounded-md bg-red-50 p-4">
            <div className="text-sm text-red-700">{bookingError}</div>
          </div>
        )}

        {bookingSuccess && (
          <div className="mb-4 rounded-md bg-green-50 p-4">
            <div className="text-sm text-green-700">{bookingSuccess}</div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Список зон */}
          <div className="card">
            <h2 className="text-xl font-semibold mb-4">Зоны</h2>
            <div className="space-y-2">
              {zones.map((zone) => (
                <button
                  key={zone.id}
                  onClick={() => handleZoneSelect(zone)}
                  className={`w-full text-left p-4 rounded-lg border-2 transition-colors ${
                    selectedZone?.id === zone.id
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="font-medium">{zone.name}</div>
                  {zone.address && (
                    <div className="text-sm text-gray-500 mt-1">{zone.address}</div>
                  )}
                </button>
              ))}
              {zones.length === 0 && (
                <p className="text-gray-500 text-center py-4">Нет доступных зон</p>
              )}
            </div>
          </div>

          {/* Список мест */}
          <div className="card">
            <h2 className="text-xl font-semibold mb-4">Места</h2>
            {!selectedZone ? (
              <p className="text-gray-500 text-center py-4">Выберите зону</p>
            ) : (
              <div className="space-y-2">
                {places.map((place) => (
                  <button
                    key={place.id}
                    onClick={() => handlePlaceSelect(place)}
                    className={`w-full text-left p-4 rounded-lg border-2 transition-colors ${
                      selectedPlace?.id === place.id
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="font-medium">{place.name}</div>
                  </button>
                ))}
                {places.length === 0 && (
                  <p className="text-gray-500 text-center py-4">Нет доступных мест</p>
                )}
              </div>
            )}
          </div>

          {/* Слоты */}
          <div className="card">
            <h2 className="text-xl font-semibold mb-4">Доступные слоты</h2>
            {!selectedPlace ? (
              <p className="text-gray-500 text-center py-4">Выберите место</p>
            ) : (
              <>
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Дата
                  </label>
                  <input
                    type="date"
                    value={selectedDate}
                    onChange={(e) => handleDateChange(e.target.value)}
                    min={new Date().toISOString().split('T')[0]}
                    className="input-field"
                  />
                </div>

                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {slots.map((slot) => (
                    <div
                      key={slot.id}
                      className={`p-4 rounded-lg border-2 ${
                        slot.is_available
                          ? 'border-green-200 bg-green-50'
                          : 'border-gray-200 bg-gray-50'
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <div>
                          <div className="font-medium">
                            {new Date(slot.start_time).toLocaleTimeString('ru-RU', {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}{' '}
                            -{' '}
                            {new Date(slot.end_time).toLocaleTimeString('ru-RU', {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </div>
                          <div className="text-sm text-gray-600">
                            {slot.is_available ? 'Доступно' : 'Занято'}
                          </div>
                        </div>
                        {slot.is_available && (
                          <button
                            onClick={() => handleBookSlot(slot.id)}
                            disabled={bookingSlot === slot.id}
                            className="btn-primary text-sm disabled:opacity-50"
                          >
                            {bookingSlot === slot.id ? 'Бронирую...' : 'Забронировать'}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                  {slots.length === 0 && (
                    <p className="text-gray-500 text-center py-4">
                      Нет доступных слотов на эту дату
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
