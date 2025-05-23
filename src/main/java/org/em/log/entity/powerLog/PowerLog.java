package org.em.log.entity.powerLog;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
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
public class PowerLog extends BaseEntity {

    @Id
    @GeneratedValue
    private Long id;

    @Embedded
    DeviceIdentifier deviceIdentifier;

    @Embedded
    GpsInfo gpsInfo;

    @Column(nullable = false)
    private PowerStatus powerStatus;

    @Column(nullable = false)
    private LocalDateTime powerTime;


    private Integer totalTripMeter;

    @Builder
    public PowerLog(
            DeviceIdentifier deviceIdentifier,
            PowerStatus powerStatus,
            LocalDateTime powerTime,
            GpsInfo gpsInfo,
            Integer totalTripMeter
    ){
        this.deviceIdentifier = deviceIdentifier;
        this.powerStatus = powerStatus;
        this.powerTime = powerTime;
        this.gpsInfo = gpsInfo;
        this.totalTripMeter = totalTripMeter;
    }
}
