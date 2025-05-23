package org.em.log.entity.geofenceLog;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.em.log.entity.common.DeviceIdentifier;
import org.em.log.entity.common.GpsInfo;

@Entity
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class GeofenceLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    DeviceIdentifier deviceIdentifier;

    @Column(nullable = false)
    private Long geofenceGroupId;

    @Column(nullable = false)
    private Long geofenceId;

    @Column(nullable = false)
    private boolean eventVal;

    @Embedded
    GpsInfo gpsInfo;

    @Column(nullable = false)
    private Integer angle;

    @Column(nullable = false)
    private LocalDateTime occurredTime;

    @Builder
    public GeofenceLog(
        DeviceIdentifier deviceIdentifier,
        Long geofence,
        Long geofenceGroupId,
        boolean eventVal,
        GpsInfo gpsInfo,
        Integer angle,
        LocalDateTime occurredTime
    ) {
        this.deviceIdentifier = deviceIdentifier;
        this.geofenceId = geofence;
        this.geofenceGroupId = geofenceGroupId;
        this.eventVal = eventVal;
        this.gpsInfo = gpsInfo;
        this.angle = angle;
        this.occurredTime = occurredTime;
    }
}
