import { useEffect, useState, useCallback, useRef } from 'react';
import { ActivityIndicator, Alert, FlatList, Image, Pressable, StyleSheet, View } from 'react-native';
import Slider from '@react-native-community/slider';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { GradientScreen, Text, colors, fonts, fontSizes, spacing, radii } from '@/components/ui';
import { LocationPicker } from '@/components/LocationPicker';
import { getUid } from '@/services/auth';
import { apiFetch } from '@/services/api';
import { RangeSlider } from '@/components/RangeSlider';

type NearbyUser = {
  id: string;
  username: string;
  displayName: string;
  profilePhoto?: string | null;
  location?: { coordinates?: [number, number]; label?: string | null } | null;
};

/** Haversine distance in miles between two [lng, lat] points. */
function distanceMiles(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const [lng1, lat1] = a;
  const [lng2, lat2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 3958.8 * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

function formatDistance(miles: number): string {
  if (miles < 1) return '< 1 mi';
  return `${Math.round(miles)} mi`;
}

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
  const [followingSet, setFollowingSet] = useState<Set<string>>(new Set());
  const [followLoadingIds, setFollowLoadingIds] = useState<Set<string>>(new Set());
  const [minAge, setMinAge] = useState(18);
  const [maxAge, setMaxAge] = useState(99);
  const ageInitialized = useRef(false);

  /** Fetch the set of user IDs the current user follows */
  const loadFollowing = useCallback(async () => {
    try {
      const data = await apiFetch<{ following: { id: string }[] }>('/follows/following');
      setFollowingSet(new Set(data.following.map((u) => u.id)));
    } catch {
      // ignore
    }
  }, []);

  /** Toggle follow / unfollow for a user */
  const toggleFollow = useCallback(async (uid: string) => {
    setFollowLoadingIds((prev) => new Set(prev).add(uid));
    try {
      const isFollowing = followingSet.has(uid);
      const method = isFollowing ? 'DELETE' : 'POST';
      await apiFetch(`/follows/${uid}`, { method });
      setFollowingSet((prev) => {
        const next = new Set(prev);
        if (isFollowing) next.delete(uid);
        else next.add(uid);
        return next;
      });
    } catch {
      Alert.alert('Error', 'Could not update follow status');
    } finally {
      setFollowLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(uid);
        return next;
      });
    }
  }, [followingSet]);

  /** Fetch the user's profile to get their saved location */
  const loadProfileLocation = useCallback(async (): Promise<{ coordinates: [number, number]; label?: string | null } | null> => {
    try {
      const profile = await apiFetch<{ birthday?: string | null; location?: { coordinates?: [number, number]; label?: string | null } }>('/profile');
      // Center age slider on user's age
      if (!ageInitialized.current && profile.birthday) {
        const dob = new Date(profile.birthday);
        const today = new Date();
        const userAge = today.getFullYear() - dob.getFullYear() - (today < new Date(today.getFullYear(), dob.getMonth(), dob.getDate()) ? 1 : 0);
        setMinAge(Math.max(18, userAge - 2));
        setMaxAge(Math.min(99, userAge + 2));
        ageInitialized.current = true;
      }
      if (profile.location?.coordinates) {
        setProfileLocation(profile.location as any);
        return profile.location as any;
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
      const radiusKm = Math.round(radiusMiles * 1.60934);
      let url = `/profile/nearby?lng=${lng}&lat=${lat}&radius=${radiusKm}`;
      if (minAge > 18) url += `&min_age=${minAge}`;
      if (maxAge < 99) url += `&max_age=${maxAge}`;
      const data = await apiFetch<{ items: NearbyUser[] }>(url);
      setUsers(data.items ?? []);
    } catch (err: any) {
      setError(err.message ?? 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }, [radiusMiles, minAge, maxAge]);

  /** Main load: check profile location first, then fetch */
  const fetchNearby = useCallback(async () => {
    setLoading(true);
    const loc = profileLocation ?? await loadProfileLocation();
    loadFollowing();
    if (loc?.coordinates) {
      await fetchNearbyWithCoords(loc.coordinates[0], loc.coordinates[1]);
    } else {
      setLoading(false);
      setNeedsLocation(true);
    }
  }, [profileLocation, loadProfileLocation, fetchNearbyWithCoords, loadFollowing]);

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
      await apiFetch('/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
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

  const renderUser = ({ item }: { item: NearbyUser }) => {
    const dist =
      profileLocation?.coordinates && item.location?.coordinates
        ? distanceMiles(profileLocation.coordinates, item.location.coordinates)
        : null;
    const isFollowing = followingSet.has(item.id);
    const isLoadingFollow = followLoadingIds.has(item.id);

    return (
      <Pressable
        style={styles.userCard}
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
          <Text muted style={styles.username}>@{item.username}</Text>
          {(item.location?.label || dist != null) && (
            <View style={styles.locationRow}>
              {item.location?.label && (
                <>
                  <Ionicons name="location" size={11} color={colors.brandRed} />
                  <Text muted style={styles.locationText}>{item.location.label}</Text>
                </>
              )}
              {dist != null && (
                <Text muted style={styles.distText}>
                  {item.location?.label ? ' · ' : ''}{formatDistance(dist)}
                </Text>
              )}
            </View>
          )}
        </View>
        {item.id !== getUid() && (
          <Pressable
            style={[styles.followBtn, isFollowing && styles.followBtnActive]}
            onPress={() => toggleFollow(item.id)}
            disabled={isLoadingFollow}
          >
            {isLoadingFollow ? (
              <ActivityIndicator size="small" color={isFollowing ? colors.foreground : colors.primaryForeground} />
            ) : (
              <Text style={[styles.followBtnText, isFollowing && styles.followBtnTextActive]}>
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            )}
          </Pressable>
        )}
      </Pressable>
    );
  };

  return (
    <GradientScreen>
      {/* ── Header ── */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.foreground} />
        </Pressable>
        <Text style={styles.headerTitle}>Nearby</Text>
        <View style={styles.backButton} />
      </View>

      {/* ── Radius control ── */}
      {!needsLocation && (
        <View style={styles.radiusCard}>
          <View style={styles.radiusHeader}>
            <Ionicons name="radio-outline" size={16} color={colors.foreground} />
            <Text style={styles.radiusLabel}>Search Radius</Text>
            <View style={styles.radiusValueBadge}>
              <Text style={styles.radiusValue}>{radiusMiles} mi</Text>
            </View>
          </View>
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
          <View style={styles.sliderTicks}>
            <Text muted style={styles.tickText}>1 mi</Text>
            <Text muted style={styles.tickText}>200 mi</Text>
          </View>
        </View>
      )}

      {/* ── Age filter ── */}
      {!needsLocation && (
        <View style={styles.radiusCard}>
          <View style={styles.radiusHeader}>
            <Ionicons name="people-outline" size={16} color={colors.foreground} />
            <Text style={styles.radiusLabel}>Age Range</Text>
            <View style={styles.radiusValueBadge}>
              <Text style={styles.radiusValue}>{minAge} – {maxAge}</Text>
            </View>
          </View>
          <RangeSlider
            min={18}
            max={99}
            step={1}
            low={minAge}
            high={maxAge}
            onValuesChange={(lo, hi) => { setMinAge(lo); setMaxAge(hi); }}
            onSlidingComplete={() => {
              if (profileLocation?.coordinates) {
                fetchNearbyWithCoords(profileLocation.coordinates[0], profileLocation.coordinates[1]);
              }
            }}
            minGap={4}
            activeTrackColor={colors.primary}
            thumbColor={colors.primary}
            trackColor={colors.border}
            style={styles.ageRangeSlider}
          />
          <View style={styles.sliderTicks}>
            <Text muted style={styles.tickText}>18</Text>
            <Text muted style={styles.tickText}>99</Text>
          </View>
        </View>
      )}

      {/* ── Results count ── */}
      {!loading && !needsLocation && !error && users.length > 0 && (
        <View style={styles.resultsBanner}>
          <Text muted style={styles.resultsText}>
            {users.length} {users.length === 1 ? 'person' : 'people'} found nearby
          </Text>
        </View>
      )}

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text muted style={styles.loadingText}>Finding people nearby…</Text>
        </View>
      ) : needsLocation ? (
        <View style={styles.center}>
          <View style={styles.emptyIcon}>
            <Ionicons name="location-outline" size={48} color={colors.mutedForeground} />
          </View>
          <Text style={styles.emptyTitle}>Location Not Set</Text>
          <Text muted style={styles.emptySubtitle}>
            Set your location to discover nearby users.{'\n'}This will also save it to your profile.
          </Text>
          <Pressable onPress={setLocationFromGPS} style={styles.primaryPill} disabled={settingLocation}>
            {settingLocation ? (
              <ActivityIndicator size="small" color={colors.primaryForeground} />
            ) : (
              <>
                <Ionicons name="navigate" size={16} color={colors.primaryForeground} />
                <Text style={styles.pillText}>Use My Current Location</Text>
              </>
            )}
          </Pressable>
          <Pressable onPress={() => setMapPickerVisible(true)} style={styles.secondaryPill}>
            <Ionicons name="map-outline" size={16} color={colors.foreground} />
            <Text style={styles.secondaryPillText}>Pick on Map</Text>
          </Pressable>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <View style={styles.emptyIcon}>
            <Ionicons name="alert-circle-outline" size={48} color={colors.mutedForeground} />
          </View>
          <Text style={styles.emptyTitle}>Something went wrong</Text>
          <Text muted style={styles.emptySubtitle}>{error}</Text>
          <Pressable onPress={fetchNearby} style={styles.primaryPill}>
            <Ionicons name="refresh" size={16} color={colors.primaryForeground} />
            <Text style={styles.pillText}>Retry</Text>
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
              <View style={styles.emptyIcon}>
                <Ionicons name="people-outline" size={48} color={colors.mutedForeground} />
              </View>
              <Text style={styles.emptyTitle}>No one nearby</Text>
              <Text muted style={styles.emptySubtitle}>
                Try increasing the search radius{'\n'}or check back later.
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
            await apiFetch('/profile', {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
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

const AVATAR_SIZE = 48;

const styles = StyleSheet.create({
  // ── Header ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.sm,
  },
  headerTitle: {
    fontSize: fontSizes.xl,
    ...fonts.bold,
    color: colors.foreground,
  },
  backButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
  },

  // ── Radius card ──
  radiusCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    padding: spacing.md,
  },
  radiusHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  radiusLabel: {
    fontSize: fontSizes.sm,
    ...fonts.semibold,
    color: colors.foreground,
    flex: 1,
  },
  radiusValueBadge: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 3,
    borderRadius: radii.full,
  },
  radiusValue: {
    color: colors.primaryForeground,
    fontSize: fontSizes.xs,
    ...fonts.bold,
  },
  slider: {
    width: '100%',
    height: 36,
    marginTop: spacing.xs,
  },
  sliderTicks: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: -4,
  },
  tickText: {
    fontSize: 11,
  },

  // ── Results banner ──
  resultsBanner: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  resultsText: {
    fontSize: fontSizes.xs,
    ...fonts.medium,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },

  // ── List ──
  list: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },

  // ── User card ──
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    padding: spacing.md,
    marginBottom: spacing.sm,
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
    ...fonts.bold,
    fontSize: fontSizes.base,
  },
  userInfo: {
    flex: 1,
    gap: 1,
  },
  displayName: {
    ...fonts.semibold,
    fontSize: fontSizes.base,
    color: colors.foreground,
  },
  username: {
    fontSize: fontSizes.sm,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginTop: 2,
  },
  locationText: {
    fontSize: fontSizes.xs,
  },
  distText: {
    fontSize: fontSizes.xs,
  },

  // ── Follow button ──
  followBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.full,
    minWidth: 84,
    alignItems: 'center',
  },
  followBtnActive: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  followBtnText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
  followBtnTextActive: {
    color: colors.foreground,
  },

  // ── Center / empty states ──
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
  },
  loadingText: {
    marginTop: spacing.md,
    fontSize: fontSizes.sm,
  },
  emptyIcon: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  emptyTitle: {
    fontSize: fontSizes.lg,
    ...fonts.semibold,
    color: colors.foreground,
    marginBottom: spacing.xs,
  },
  emptySubtitle: {
    fontSize: fontSizes.sm,
    textAlign: 'center',
    lineHeight: 20,
  },

  // ── Pill buttons ──
  primaryPill: {
    marginTop: spacing.lg,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.full,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  pillText: {
    color: colors.primaryForeground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },
  secondaryPill: {
    marginTop: spacing.sm,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.full,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  secondaryPillText: {
    color: colors.foreground,
    ...fonts.semibold,
    fontSize: fontSizes.sm,
  },

  // ── Age filter ──
  ageRangeSlider: {
    marginTop: spacing.xs,
  },
});
