import { useEffect, useState, useCallback } from 'react';
import { ActivityIndicator, Alert, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import Slider from '@react-native-community/slider';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { GradientScreen, Text, colors, spacing } from '@/components/ui';
import { LocationPicker } from '@/components/LocationPicker';
import { getIdToken } from '@/services/auth';
import { config } from '@/config';

type NearbyUser = {
  id: string;
  username: string;
  displayName: string;
  profilePhoto?: string | null;
  location?: { label?: string | null } | null;
};

export default function FriendsScreen() {
  const router = useRouter();
  const [users, setUsers] = useState<NearbyUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [radiusMiles, setRadiusMiles] = useState(25);
  const [needsLocation, setNeedsLocation] = useState(false);
  const [settingLocation, setSettingLocation] = useState(false);
  const [profileLocation, setProfileLocation] = useState<{ coordinates: [number, number]; label?: string | null } | null>(null);
  const [mapPickerVisible, setMapPickerVisible] = useState(false);

  /** Fetch the user's profile to get their saved location */
  const loadProfileLocation = useCallback(async (): Promise<{ coordinates: [number, number]; label?: string | null } | null> => {
    try {
      const token = getIdToken();
      const res = await fetch(`${config.apiBaseUrl}/profile`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) return null;
      const profile = await res.json();
      if (profile.location?.coordinates) {
        setProfileLocation(profile.location);
        return profile.location;
      }
      return null;
    } catch {
      return null;
    }
  }, []);

  /** Fetch nearby users using the given coordinates */
  const fetchNearbyWithCoords = useCallback(async (lng: number, lat: number) => {
    setLoading(true);
    setError(null);
    setNeedsLocation(false);
    try {
      const token = getIdToken();
      const radiusKm = Math.round(radiusMiles * 1.60934);
      const params = new URLSearchParams({
        lng: String(lng),
        lat: String(lat),
        radius: String(radiusKm),
      });
      const res = await fetch(`${config.apiBaseUrl}/profile/nearby?${params}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Failed to fetch nearby users');
      const data = await res.json();
      setUsers(data.items ?? []);
    } catch (err: any) {
      setError(err.message ?? 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }, [radiusMiles]);

  /** Main load: check profile location first, then fetch */
  const fetchNearby = useCallback(async () => {
    setLoading(true);
    const loc = profileLocation ?? await loadProfileLocation();
    if (loc?.coordinates) {
      await fetchNearbyWithCoords(loc.coordinates[0], loc.coordinates[1]);
    } else {
      setLoading(false);
      setNeedsLocation(true);
    }
  }, [profileLocation, loadProfileLocation, fetchNearbyWithCoords]);

  /** Use GPS to set location on the profile, then search */
  const setLocationFromGPS = async () => {
    try {
      setSettingLocation(true);
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Enable location permissions in Settings to use this feature.');
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const coords: [number, number] = [pos.coords.longitude, pos.coords.latitude];

      // Reverse geocode for label
      const [geo] = await Location.reverseGeocodeAsync({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
      const label = geo ? [geo.city, geo.region].filter(Boolean).join(', ') : null;

      // Save to profile
      const token = getIdToken();
      await fetch(`${config.apiBaseUrl}/profile`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ location: { type: 'Point', coordinates: coords, label } }),
      });

      const loc = { coordinates: coords, label };
      setProfileLocation(loc);
      setNeedsLocation(false);

      // Now fetch nearby users
      await fetchNearbyWithCoords(coords[0], coords[1]);
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not get location');
    } finally {
      setSettingLocation(false);
    }
  };

  useEffect(() => {
    fetchNearby();
  }, [fetchNearby]);

  const renderUser = ({ item }: { item: NearbyUser }) => (
    <Pressable
      style={styles.userRow}
      onPress={() => router.push(`/user/${item.username}` as any)}
    >
      {item.profilePhoto ? (
        <Image source={{ uri: item.profilePhoto }} style={styles.avatar} />
      ) : (
        <View style={styles.avatarFallback}>
          <Text style={styles.avatarText}>{item.displayName.charAt(0).toUpperCase()}</Text>
        </View>
      )}
      <View style={styles.userInfo}>
        <Text style={styles.displayName}>{item.displayName}</Text>
        <Text muted>@{item.username}</Text>
        {item.location?.label && (
          <View style={styles.locationRow}>
            <Ionicons name="location-outline" size={12} color={colors.mutedForeground} />
            <Text muted style={styles.locationText}>{item.location.label}</Text>
          </View>
        )}
      </View>
    </Pressable>
  );

  return (
    <GradientScreen>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </Pressable>
        <Text variant="heading">Nearby</Text>
        <View style={styles.backButton} />
      </View>

      {/* Radius slider */}
      <View style={styles.sliderSection}>
        <Text style={styles.sliderLabel}>{radiusMiles} {radiusMiles === 1 ? 'mile' : 'miles'}</Text>
        <Slider
          style={styles.slider}
          minimumValue={1}
          maximumValue={200}
          step={1}
          value={radiusMiles}
          onValueChange={setRadiusMiles}
          onSlidingComplete={() => {
            if (profileLocation?.coordinates) {
              fetchNearbyWithCoords(profileLocation.coordinates[0], profileLocation.coordinates[1]);
            }
          }}
          minimumTrackTintColor={colors.primary}
          maximumTrackTintColor={colors.border}
          thumbTintColor={colors.primary}
        />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text muted style={{ marginTop: spacing.md }}>Finding people nearby…</Text>
        </View>
      ) : needsLocation ? (
        <View style={styles.center}>
          <Ionicons name="location-outline" size={48} color={colors.mutedForeground} />
          <Text style={{ marginTop: spacing.md, fontWeight: '600', fontSize: 16 }}>
            Location Not Set
          </Text>
          <Text muted style={{ marginTop: spacing.xs, textAlign: 'center', paddingHorizontal: spacing.xl }}>
            Set your location to discover nearby users. This will also save it to your profile.
          </Text>
          <Pressable onPress={setLocationFromGPS} style={styles.setLocationButton} disabled={settingLocation}>
            {settingLocation ? (
              <ActivityIndicator size="small" color={colors.primaryForeground} />
            ) : (
              <>
                <Ionicons name="navigate" size={16} color={colors.primaryForeground} />
                <Text style={styles.setLocationText}>Use My Current Location</Text>
              </>
            )}
          </Pressable>
          <Pressable onPress={() => setMapPickerVisible(true)} style={styles.pickOnMapButton}>
            <Ionicons name="map-outline" size={16} color={colors.primaryForeground} />
            <Text style={styles.setLocationText}>Pick on Map</Text>
          </Pressable>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Ionicons name="alert-circle-outline" size={40} color={colors.mutedForeground} />
          <Text muted style={{ marginTop: spacing.md, textAlign: 'center', paddingHorizontal: spacing.lg }}>
            {error}
          </Text>
          <Pressable onPress={fetchNearby} style={styles.retryButton}>
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={users}
          keyExtractor={(item) => item.id}
          renderItem={renderUser}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.center}>
              <Ionicons name="people-outline" size={40} color={colors.mutedForeground} />
              <Text muted style={{ marginTop: spacing.md }}>No users found nearby.</Text>
              <Text muted style={{ fontSize: 12, marginTop: spacing.xs }}>
                Try increasing the radius or check back later.
              </Text>
            </View>
          }
        />
      )}

      <LocationPicker
        visible={mapPickerVisible}
        onClose={() => setMapPickerVisible(false)}
        initialCoords={profileLocation?.coordinates ?? null}
        onSelect={async (loc) => {
          setMapPickerVisible(false);
          try {
            setSettingLocation(true);
            // Save to profile
            const token = getIdToken();
            await fetch(`${config.apiBaseUrl}/profile`, {
              method: 'PATCH',
              headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              },
              body: JSON.stringify({ location: { type: 'Point', coordinates: loc.coordinates, label: loc.label } }),
            });
            const saved = { coordinates: loc.coordinates, label: loc.label };
            setProfileLocation(saved);
            setNeedsLocation(false);
            await fetchNearbyWithCoords(loc.coordinates[0], loc.coordinates[1]);
          } catch (err: any) {
            Alert.alert('Error', err.message ?? 'Could not save location');
          } finally {
            setSettingLocation(false);
          }
        }}
      />
    </GradientScreen>
  );
}

const AVATAR_SIZE = 44;

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  backButton: {
    width: 40,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sliderSection: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  sliderLabel: {
    textAlign: 'center',
    fontSize: 14,
    fontWeight: '600',
    color: colors.foreground,
    marginBottom: spacing.xs,
  },
  slider: {
    width: '100%',
    height: 40,
  },
  list: {
    paddingHorizontal: spacing.lg,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    gap: spacing.md,
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarFallback: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 16,
  },
  userInfo: {
    flex: 1,
    gap: 2,
  },
  displayName: {
    fontWeight: '600',
    fontSize: 15,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginTop: 2,
  },
  locationText: {
    fontSize: 12,
  },
  retryButton: {
    marginTop: spacing.md,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 8,
  },
  retryText: {
    color: colors.primaryForeground,
    fontWeight: '600',
  },
  setLocationButton: {
    marginTop: spacing.lg,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm + 2,
    borderRadius: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  setLocationText: {
    color: colors.primaryForeground,
    fontWeight: '600',
    fontSize: 15,
  },
  pickOnMapButton: {
    marginTop: spacing.sm,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm + 2,
    borderRadius: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    opacity: 0.85,
  },
});
