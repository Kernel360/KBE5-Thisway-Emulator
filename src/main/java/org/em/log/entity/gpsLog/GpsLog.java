package org.em.log.entity.gpsLog;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.em.common.BaseEntity;
import org.em.log.entity.common.DeviceIdentifier;
import org.em.log.entity.common.GpsInfo;

@Entity
@Getter
@NoArgsConstructor(access = lombok.AccessLevel.PROTECTED)
public class GpsLog extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    DeviceIdentifier deviceIdentifier;

    @Embedded
    GpsInfo gpsInfo;

    @Column(nullable = false)
    private Integer angle;

    @Column(nullable = false)
    private Integer speed;

    @Column(nullable = false)
    private Integer totalTripMeter;

    @Column(nullable = false)
    private Integer batteryVoltage;

    @Column(nullable = false)
    private LocalDateTime occurredTime;

    @Builder
    public GpsLog(
            DeviceIdentifier deviceIdentifier,
            GpsInfo gpsInfo,
            Integer angle,
            Integer speed,
            Integer totalTripMeter,
            Integer batteryVoltage,
            LocalDateTime occurredTime
    ){
        this.deviceIdentifier = deviceIdentifier;
        this.gpsInfo = gpsInfo;
        this.angle = angle;
        this.speed = speed;
        this.totalTripMeter = totalTripMeter;
        this.batteryVoltage = batteryVoltage;
        this.occurredTime = occurredTime;
    }
}
