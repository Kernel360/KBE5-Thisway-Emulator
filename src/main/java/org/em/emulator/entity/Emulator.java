package org.em.emulator.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.em.common.BaseEntity;

@Entity
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Emulator extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long mdn;

    @Column(nullable = false)
    private Long vehicleId;

    @Column(nullable = false)
    private String terminalId;

    @Column(nullable = false)
    private Integer manufactureId;

    @Column(nullable = false)
    private Integer packetVersion;

    @Column(nullable = false)
    private Integer deviceId;

    @Column(nullable = false)
    private String deviceFirmwareVersion;

    @Builder
    public Emulator(
            Long vehicleId,
            String terminalId,
            Integer manufactureId,
            Integer packetVersion,
            Integer deviceId,
            String deviceFirmwareVersion
    ) {
        this.vehicleId = vehicleId;
        this.terminalId = terminalId;
        this.manufactureId = manufactureId;
        this.packetVersion = packetVersion;
        this.deviceId = deviceId;
        this.deviceFirmwareVersion = deviceFirmwareVersion;
    }
}
