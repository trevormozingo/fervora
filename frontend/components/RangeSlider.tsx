import { useRef } from 'react';
import { View, PanResponder, StyleSheet, type ViewStyle } from 'react-native';

const THUMB_SIZE = 24;
const TRACK_HEIGHT = 4;

type Props = {
  min: number;
  max: number;
  step?: number;
  minGap?: number;
  low: number;
  high: number;
  onValuesChange: (low: number, high: number) => void;
  onSlidingComplete?: (low: number, high: number) => void;
  trackColor?: string;
  activeTrackColor?: string;
  thumbColor?: string;
  style?: ViewStyle;
};

export function RangeSlider({
  min,
  max,
  step = 1,
  minGap = 1,
  low,
  high,
  onValuesChange,
  onSlidingComplete,
  trackColor = '#e0e0e0',
  activeTrackColor = '#007AFF',
  thumbColor = '#007AFF',
  style,
}: Props) {
  const trackWidth = useRef(0);
  const lowRef = useRef(low);
  const highRef = useRef(high);
  const startPos = useRef(0);

  lowRef.current = low;
  highRef.current = high;

  const snap = (val: number) => Math.round(val / step) * step;

  const posToVal = (x: number) => {
    const ratio = Math.max(0, Math.min(1, x / trackWidth.current));
    return snap(min + ratio * (max - min));
  };

  const valToPos = (val: number) => ((val - min) / (max - min)) * trackWidth.current;

  const createResponder = (which: 'low' | 'high') =>
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        startPos.current = valToPos(which === 'low' ? lowRef.current : highRef.current);
      },
      onPanResponderMove: (_, gs) => {
        const newVal = posToVal(startPos.current + gs.dx);
        if (which === 'low') {
          const clamped = Math.max(min, Math.min(newVal, highRef.current - minGap));
          if (clamped !== lowRef.current) onValuesChange(clamped, highRef.current);
        } else {
          const clamped = Math.min(max, Math.max(newVal, lowRef.current + minGap));
          if (clamped !== highRef.current) onValuesChange(lowRef.current, clamped);
        }
      },
      onPanResponderRelease: () => {
        onSlidingComplete?.(lowRef.current, highRef.current);
      },
    });

  const lowResponder = useRef(createResponder('low')).current;
  const highResponder = useRef(createResponder('high')).current;

  const lowPos = trackWidth.current > 0 ? valToPos(low) : 0;
  const highPos = trackWidth.current > 0 ? valToPos(high) : 0;

  return (
    <View
      style={[styles.container, style]}
      onLayout={(e) => {
        trackWidth.current = e.nativeEvent.layout.width - THUMB_SIZE;
      }}
    >
      {/* Background track */}
      <View style={[styles.track, { backgroundColor: trackColor }]} />
      {/* Active range track */}
      <View
        style={[
          styles.activeTrack,
          {
            backgroundColor: activeTrackColor,
            left: lowPos + THUMB_SIZE / 2,
            width: highPos - lowPos,
          },
        ]}
      />
      {/* Low thumb */}
      <View
        style={[styles.thumb, { backgroundColor: thumbColor, left: lowPos }]}
        {...lowResponder.panHandlers}
      />
      {/* High thumb */}
      <View
        style={[styles.thumb, { backgroundColor: thumbColor, left: highPos }]}
        {...highResponder.panHandlers}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    height: THUMB_SIZE + 16,
    justifyContent: 'center',
  },
  track: {
    position: 'absolute',
    left: THUMB_SIZE / 2,
    right: THUMB_SIZE / 2,
    height: TRACK_HEIGHT,
    borderRadius: TRACK_HEIGHT / 2,
  },
  activeTrack: {
    position: 'absolute',
    height: TRACK_HEIGHT,
    borderRadius: TRACK_HEIGHT / 2,
  },
  thumb: {
    position: 'absolute',
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: THUMB_SIZE / 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 3,
  },
});
